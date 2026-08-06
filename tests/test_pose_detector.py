import numpy as np
from pose_detector import PoseDetector


def test_no_person_returns_none():
    detector = PoseDetector()
    try:
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(blank_frame)
        assert result is None
    finally:
        detector.close()


def test_detect_does_not_crash_on_multiple_frames():
    detector = PoseDetector()
    try:
        for _ in range(3):
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detector.detect(blank_frame)
    finally:
        detector.close()
