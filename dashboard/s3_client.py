"""S3 영상 저장소 클라이언트.

운동 녹화 영상을 S3에 업로드/다운로드하기 위한 Presigned URL을 생성한다.
"""

import boto3

REGION = "us-east-1"
VIDEO_BUCKET = "careflow-exercise-videos"

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=REGION)
    return _s3_client


def generate_upload_url(patient_id, session_id, exercise_key, expires_in=600):
    """영상 업로드용 Presigned URL을 생성한다.

    Args:
        patient_id: 환자 ID
        session_id: 세션 ID
        exercise_key: 운동 키
        expires_in: URL 유효 시간(초), 기본 10분

    Returns:
        dict: {"upload_url": str, "s3_key": str}
    """
    s3_key = f"videos/{patient_id}/{session_id}_{exercise_key}.webm"
    client = _get_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": VIDEO_BUCKET,
            "Key": s3_key,
            "ContentType": "video/webm",
        },
        ExpiresIn=expires_in,
    )
    return {"upload_url": url, "s3_key": s3_key}


def generate_download_url(s3_key, expires_in=1800):
    """영상 다운로드(재생)용 Presigned URL을 생성한다.

    Args:
        s3_key: S3 객체 키
        expires_in: URL 유효 시간(초), 기본 30분

    Returns:
        str: Presigned download URL
    """
    client = _get_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": VIDEO_BUCKET,
            "Key": s3_key,
        },
        ExpiresIn=expires_in,
    )
    return url


def upload_video_file(local_path, s3_key):
    """로컬 영상 파일을 S3에 직접 업로드한다 (서버 사이드 업로드용).

    카카오톡에서 받은 영상을 분석 후 S3에 보관할 때 사용.
    """
    client = _get_client()
    client.upload_file(
        local_path,
        VIDEO_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": "video/webm"},
    )
    return s3_key


def delete_video(s3_key):
    """S3에서 영상을 삭제한다."""
    client = _get_client()
    client.delete_object(Bucket=VIDEO_BUCKET, Key=s3_key)
