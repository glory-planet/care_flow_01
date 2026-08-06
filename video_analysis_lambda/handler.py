"""영상 분석 Lambda 핸들러.

S3에 업로드된 운동 영상을 분석하여:
1. MediaPipe로 관절을 추출하고
2. 관절 각도 변화로 "운동 중" 구간을 식별하고
3. 운동 구간만 편집(잘라내기)해서 새 파일로 S3에 저장하고
4. 운동하지 않은 구간은 삭제하고
5. 분석 결과(반복 횟수, 운동 구간)를 DynamoDB에 기록한다.

이 Lambda는 Docker Container Image로 배포된다 (OpenCV + MediaPipe 포함).
트리거: S3 PutObject 이벤트 또는 SQS를 통한 비동기 호출.
"""

import json
import os
import tempfile

import boto3
import cv2

from main import build_trackers, get_tracker_value
from pose_detector import PoseDetector

REGION = "us-east-1"
VIDEO_BUCKET = "careflow-exercise-videos"
DYNAMO_TABLE_SESSIONS = "CareFlow-Sessions"

# 운동 구간 판별 설정
IDLE_THRESHOLD_SECONDS = 7  # 7초 이상 움직임 없으면 운동 중이 아닌 것으로 판단

s3 = boto3.client("s3", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event, context):
    """S3 이벤트 또는 직접 호출로 영상 분석을 수행한다."""

    # S3 이벤트에서 영상 정보 추출
    if "Records" in event:
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
    else:
        bucket = event.get("bucket", VIDEO_BUCKET)
        key = event["s3_key"]

    exercise_key = event.get("exercise_key")
    patient_id = event.get("patient_id")
    session_id = event.get("session_id")

    # S3에서 영상 다운로드
    local_path = os.path.join(tempfile.gettempdir(), "input_video.webm")
    s3.download_file(bucket, key, local_path)

    # 분석 실행
    result = analyze_and_trim(local_path, exercise_key)

    # 운동 구간 영상만 S3에 업로드
    if result["trimmed_path"] and os.path.exists(result["trimmed_path"]):
        trimmed_key = key.replace(".webm", "_trimmed.webm")
        s3.upload_file(result["trimmed_path"], bucket, trimmed_key, ExtraArgs={"ContentType": "video/webm"})
        # 원본 삭제 (운동 안 한 구간 포함)
        s3.delete_object(Bucket=bucket, Key=key)
        final_s3_key = trimmed_key
    else:
        final_s3_key = key

    # DynamoDB 세션 업데이트
    if session_id and patient_id:
        table = dynamodb.Table(DYNAMO_TABLE_SESSIONS)
        table.update_item(
            Key={"patient_id": patient_id, "session_id": session_id},
            UpdateExpression="SET final_count = :fc, target_reached = :tr, analysis_status = :s, video_s3_key = :vk, rest_seconds = :rs",
            ExpressionAttributeValues={
                ":fc": result["final_count"],
                ":tr": result["target_reached"],
                ":s": "completed",
                ":vk": final_s3_key,
                ":rs": result["total_rest_seconds"],
            },
        )

    # 임시 파일 정리
    for path in [local_path, result.get("trimmed_path")]:
        if path and os.path.exists(path):
            os.remove(path)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "final_count": result["final_count"],
            "exercise_segments": result["segments"],
            "total_rest_seconds": result["total_rest_seconds"],
        }),
    }


def analyze_and_trim(video_path, exercise_key):
    """영상을 분석하여 운동 구간을 식별하고, 운동 구간만 편집한다.

    운동 구간 판별 로직:
    - 관절 각도가 운동 임계값 범위 내에서 움직이면 "운동 중"
    - 7초 이상 움직임이 없으면 "쉬는 중"으로 전환
    - 운동 중 구간만 모아서 하나의 영상으로 합침
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector = PoseDetector()
    tracker = build_trackers().get(exercise_key)

    # 프레임별 상태 기록
    frames = []
    frame_states = []  # True = 운동 중, False = 쉬는 중
    last_active_frame = 0
    idle_threshold_frames = int(IDLE_THRESHOLD_SECONDS * fps)

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        landmarks = detector.detect(frame)
        is_active = False

        if landmarks is not None:
            if tracker:
                old_count = get_tracker_value(tracker)
                tracker.update(landmarks)
                new_count = get_tracker_value(tracker)
                if new_count != old_count:
                    is_active = True
                    last_active_frame = frame_idx
            else:
                is_active = True
                last_active_frame = frame_idx

        # 마지막 활동 후 7초 이내면 여전히 "운동 중"
        if frame_idx - last_active_frame < idle_threshold_frames:
            frame_states.append(True)
        else:
            frame_states.append(False)

        frames.append(frame)
        frame_idx += 1

    cap.release()
    detector.close()

    # 운동 구간 식별
    segments = []
    in_segment = False
    seg_start = 0

    for i, active in enumerate(frame_states):
        if active and not in_segment:
            seg_start = i
            in_segment = True
        elif not active and in_segment:
            segments.append((seg_start, i))
            in_segment = False

    if in_segment:
        segments.append((seg_start, len(frame_states)))

    # 운동 구간이 없으면
    if not segments:
        return {
            "final_count": get_tracker_value(tracker) if tracker else 0,
            "target_reached": False,
            "segments": [],
            "total_rest_seconds": len(frame_states) / fps,
            "trimmed_path": None,
        }

    # 운동 구간만 편집해서 새 영상 생성
    trimmed_path = os.path.join(tempfile.gettempdir(), "trimmed_video.webm")
    fourcc = cv2.VideoWriter_fourcc(*"VP80")
    writer = cv2.VideoWriter(trimmed_path, fourcc, fps, (width, height))

    for start, end in segments:
        for i in range(start, min(end, len(frames))):
            writer.write(frames[i])

    writer.release()

    # 쉬는 시간 계산
    rest_frames = sum(1 for s in frame_states if not s)
    total_rest_seconds = round(rest_frames / fps, 1)

    final_count = get_tracker_value(tracker) if tracker else 0

    return {
        "final_count": final_count,
        "target_reached": False,  # 호출부에서 target_reps와 비교
        "segments": [{"start_sec": round(s / fps, 1), "end_sec": round(e / fps, 1)} for s, e in segments],
        "total_rest_seconds": total_rest_seconds,
        "trimmed_path": trimmed_path,
    }
