import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)


class PoseDetector:
    """MediaPipe Pose Landmarker를 감싸 BGR 프레임에서 관절 좌표를 추출한다."""

    def __init__(self, model_path="pose_landmarker_lite.task"):
        base_options = BaseOptions(model_asset_path=model_path)
        options = PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            num_poses=1,
        )
        self._landmarker = PoseLandmarker.create_from_options(options)
        self._timestamp_ms = 0

    def detect(self, frame_bgr):
        """BGR 프레임을 받아 33개 관절의 (x, y, z, visibility) 리스트를 반환한다.

        좌표 x, y는 0~1 사이의 정규화된 값이다. 사람이 감지되지 않으면 None.
        """
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        self._timestamp_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.pose_landmarks:
            return None

        landmarks = result.pose_landmarks[0]
        return [(lm.x, lm.y, lm.z, lm.visibility) for lm in landmarks]

    def close(self):
        self._landmarker.close()
