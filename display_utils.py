import ctypes

import cv2
import numpy as np


def get_screen_size():
    """Windows 화면 해상도를 (width, height)로 반환한다."""
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def scale_to_fit(frame, target_width, target_height, fill_value=128):
    """frame의 가로세로 비율을 유지한 채 target_width x target_height 안에 맞춘다.

    남는 여백은 fill_value(기본 회색)로 채운 target_width x target_height 캔버스를
    반환한다. target 크기가 0 이하면(창이 최소화된 경우 등) frame을 그대로 반환한다.
    """
    if target_width <= 0 or target_height <= 0:
        return frame

    frame_height, frame_width = frame.shape[:2]
    scale = min(target_width / frame_width, target_height / frame_height)
    new_width = max(1, int(frame_width * scale))
    new_height = max(1, int(frame_height * scale))
    resized = cv2.resize(frame, (new_width, new_height))

    canvas = np.full((target_height, target_width, 3), fill_value, dtype=np.uint8)
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    canvas[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized
    return canvas
