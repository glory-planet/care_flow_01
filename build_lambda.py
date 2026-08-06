"""Lambda 배포 패키지를 빌드하는 스크립트.

필요한 소스 파일과 의존성을 zip으로 묶어 lambda_package.zip을 생성한다.
"""

import os
import shutil
import subprocess
import sys
import zipfile

OUTPUT_ZIP = "lambda_package.zip"
BUILD_DIR = "lambda_build"

# Lambda에 포함할 소스 파일/폴더
SOURCE_FILES = [
    "lambda_handler.py",
    "dashboard/__init__.py",
    "dashboard/data_store.py",
    "dashboard/server.py",
    "dashboard/s3_client.py",
    "dashboard/cognito_client.py",
    "dashboard/llm_client.py",
    "dashboard/hospital_rag.py",
    "dashboard/kakao_skill.py",
    "dashboard/exercise_library.py",
    "dashboard/login.html",
    "dashboard/doctor.html",
    "dashboard/patient.html",
    "dashboard/patient-detail.html",
    "video_analyzer.py",
    "main.py",
    "angle_calculator.py",
    "arm_circle_tracker.py",
    "jumping_jack_tracker.py",
    "landmarks.py",
    "overhead_reach_tracker.py",
    "overhead_squat_tracker.py",
    "pose_detector.py",
    "side_leg_raise_tracker.py",
    "single_leg_stance_tracker.py",
    "squat_tracker.py",
    "wall_slide_tracker.py",
    "display_utils.py",
]

# pip로 설치할 의존성 (Lambda에 기본 제공되지 않는 것만)
DEPENDENCIES = ["flask", "aws-wsgi", "boto3"]


def build():
    # 빌드 디렉토리 초기화
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    # 의존성 설치
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        *DEPENDENCIES,
        "-t", BUILD_DIR,
        "--quiet",
    ])

    # 소스 파일 복사
    for src in SOURCE_FILES:
        dest = os.path.join(BUILD_DIR, src)
        dest_dir = os.path.dirname(dest)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        if os.path.exists(src):
            shutil.copy2(src, dest)
        else:
            print(f"WARNING: {src} not found, skipping")

    # dashboard/__init__.py가 없으면 생성
    init_path = os.path.join(BUILD_DIR, "dashboard", "__init__.py")
    if not os.path.exists(init_path):
        os.makedirs(os.path.dirname(init_path), exist_ok=True)
        open(init_path, "w").close()

    # assets 폴더 복사
    assets_src = "dashboard/assets"
    if os.path.exists(assets_src):
        shutil.copytree(assets_src, os.path.join(BUILD_DIR, "dashboard/assets"), dirs_exist_ok=True)

    # zip 생성
    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUILD_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, BUILD_DIR)
                zf.write(file_path, arc_name)

    # 정리
    shutil.rmtree(BUILD_DIR)

    size_mb = os.path.getsize(OUTPUT_ZIP) / (1024 * 1024)
    print(f"Created {OUTPUT_ZIP} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    build()
