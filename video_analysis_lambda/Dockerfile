FROM public.ecr.aws/lambda/python:3.12

# OpenCV 시스템 의존성
RUN dnf install -y mesa-libGL mesa-libGLU

# Python 의존성
COPY video_analysis_lambda/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY video_analysis_lambda/handler.py .
COPY angle_calculator.py .
COPY landmarks.py .
COPY pose_detector.py .
COPY squat_tracker.py .
COPY arm_circle_tracker.py .
COPY wall_slide_tracker.py .
COPY overhead_reach_tracker.py .
COPY overhead_squat_tracker.py .
COPY side_leg_raise_tracker.py .
COPY single_leg_stance_tracker.py .
COPY jumping_jack_tracker.py .
COPY main.py .
COPY display_utils.py .
COPY pose_landmarker_lite.task .

CMD ["handler.handler"]
