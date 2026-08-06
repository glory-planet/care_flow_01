import numpy as np

from display_utils import scale_to_fit


def test_canvas_matches_target_dimensions():
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    canvas = scale_to_fit(frame, target_width=1600, target_height=900)
    assert canvas.shape == (900, 1600, 3)


def test_pillarboxed_when_frame_is_narrower_than_target_ratio():
    # frame 640x480(4:3)을 1600x900(16:9) 안에 맞추면 세로가 꽉 차고
    # 좌우에 회색 여백(필러박스)이 생긴다.
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    canvas = scale_to_fit(frame, target_width=1600, target_height=900)

    assert (canvas[450, 0] == 128).all()  # 왼쪽 여백
    assert (canvas[450, 800] == 255).all()  # 중앙, 스케일된 프레임 영역


def test_letterboxed_when_frame_is_wider_than_target_ratio():
    # frame 1280x720(16:9)을 900x900(정사각형) 안에 맞추면 가로가 꽉 차고
    # 위아래에 회색 여백(레터박스)이 생긴다.
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    canvas = scale_to_fit(frame, target_width=900, target_height=900)

    assert (canvas[0, 450] == 128).all()  # 위쪽 여백
    assert (canvas[450, 450] == 255).all()  # 중앙, 스케일된 프레임 영역


def test_non_positive_target_returns_frame_unchanged():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    canvas = scale_to_fit(frame, target_width=0, target_height=0)
    assert canvas.shape == frame.shape
