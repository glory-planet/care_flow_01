import pytest
from angle_calculator import calculate_angle


def test_right_angle():
    # b=(0,0) 꼭짓점, a는 위쪽, c는 오른쪽 -> 90도
    angle = calculate_angle((0, 1), (0, 0), (1, 0))
    assert angle == pytest.approx(90.0, abs=0.1)


def test_straight_line_is_180_degrees():
    # a-b-c가 일직선 -> 180도
    angle = calculate_angle((-1, 0), (0, 0), (1, 0))
    assert angle == pytest.approx(180.0, abs=0.1)


def test_folded_back_is_0_degrees():
    # a와 c가 b 기준으로 같은 방향 -> 0도
    angle = calculate_angle((1, 0), (0, 0), (2, 0))
    assert angle == pytest.approx(0.0, abs=0.1)


def test_45_degree_angle():
    angle = calculate_angle((1, 0), (0, 0), (1, 1))
    assert angle == pytest.approx(45.0, abs=0.1)
