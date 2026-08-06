import math

from arm_circle_tracker import ArmCircleTracker
from tests.helpers import make_landmarks

SHOULDER = (0.5, 0.5)
RADIUS = 0.2


def point_on_circle(angle_degrees):
    theta = math.radians(angle_degrees)
    return make_landmarks(
        right_shoulder=SHOULDER,
        right_wrist=(SHOULDER[0] + RADIUS * math.cos(theta), SHOULDER[1] + RADIUS * math.sin(theta)),
    )


def test_initial_count_is_zero():
    tracker = ArmCircleTracker()
    assert tracker.update(point_on_circle(0)) == 0


def test_full_circle_counts_one():
    tracker = ArmCircleTracker()
    angles = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    counts = [tracker.update(point_on_circle(a)) for a in angles]
    assert counts[-1] == 1
    assert counts[:-1] == [0] * (len(angles) - 1)


def test_two_full_circles_counts_two():
    tracker = ArmCircleTracker()
    angles = list(range(0, 361, 45)) + list(range(45, 361, 45))
    counts = [tracker.update(point_on_circle(a)) for a in angles]
    assert counts[-1] == 2
