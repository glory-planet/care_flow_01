"""저장된 영상 파일을 프레임 단위로 분석해서 반복 횟수(또는 유지 시간)를 계산한다.

main.py의 실시간 웹캠 캡처 경로와 완전히 분리되어 있다 — `pose_detector.PoseDetector.detect()`가
BGR 프레임 + 내부 타임스탬프만 받는 구조라, 저장된 영상 파일에서 추출한 프레임을 그대로 넣어도
동작한다. 운동별 트래커(예: `SquatTracker`)도 `.update(landmarks)` 호출 하나로 상태를 누적하는
stateless-per-frame 구조라 웹캠/파일 구분 없이 재사용 가능하다 (`main.py`의 `build_trackers()`,
`get_tracker_value()`를 그대로 가져다 쓴다).

재촬영 판단 기준(확정, 설계 문서 참고): 영상 전체에서 사람이 한 번도 인식되지 않은 경우에만
`pose_detected=False`를 반환한다. 목표 횟수에 못 미치는 것은 재촬영 사유가 아니고, 그냥
`target_reached: false`로 기록만 하고 넘어간다 — 이 판단은 이 모듈이 아니라 호출부(카카오 스킬
핸들러)가 `target_reps`와 비교해서 내린다.
"""

import os
import urllib.request

from main import build_trackers, get_tracker_value
from pose_detector import PoseDetector


def download_video(url, dest_path):
    """카카오 CDN 등에서 제공하는 서명된 URL로부터 영상을 다운로드해서 dest_path에 저장한다."""
    directory = os.path.dirname(dest_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    urllib.request.urlretrieve(url, dest_path)
    return dest_path


def analyze_video(video_path, exercise_key):
    """영상 파일을 프레임 단위로 분석해서 반복 횟수와 포즈 인식 여부를 반환한다."""
    import cv2

    tracker = build_trackers()[exercise_key]
    detector = PoseDetector()
    pose_detected = False

    cap = cv2.VideoCapture(video_path)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            landmarks = detector.detect(frame)
            if landmarks is not None:
                pose_detected = True
                tracker.update(landmarks)
    finally:
        cap.release()
        detector.close()

    return {
        "pose_detected": pose_detected,
        "final_value": get_tracker_value(tracker),
    }


def delete_video_file(path):
    """분석이 끝난 다운로드 원본 영상을 삭제한다. 실패해도 조용히 넘어간다(디스크 정리 목적일 뿐)."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
