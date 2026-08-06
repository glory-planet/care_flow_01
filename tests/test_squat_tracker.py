import pytest
from squat_tracker import SquatTracker
from tests.helpers import make_landmarks

STANDING = make_landmarks(
    left_hip=(0.5, 0.3), left_knee=(0.5, 0.6), left_ankle=(0.5, 0.9)
)
SQUATTING = make_landmarks(
    left_hip=(0.5, 0.3), left_knee=(0.9, 0.6), left_ankle=(0.5, 0.9)
)


def test_initial_count_is_zero():
    tracker = SquatTracker()
    assert tracker.update(STANDING) == 0


def test_full_squat_cycle_counts_one():
    tracker = SquatTracker()
    sequence = [STANDING, STANDING, SQUATTING, SQUATTING, STANDING]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0, 0, 1]


def test_reset_clears_count():
    tracker = SquatTracker()
    tracker.update(SQUATTING)
    tracker.update(STANDING)
    assert tracker.update(STANDING) == 1
    tracker.reset()
    assert tracker.update(STANDING) == 0


def test_display_text():
    tracker = SquatTracker()
    assert tracker.display_text() == "스쿼트: 0"
