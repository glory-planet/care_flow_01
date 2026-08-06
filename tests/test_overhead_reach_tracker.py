from overhead_reach_tracker import OverheadReachTracker
from tests.helpers import make_landmarks

DOWN = make_landmarks(
    nose=(0.5, 0.2),
    left_shoulder=(0.4, 0.3), right_shoulder=(0.6, 0.3),
    left_wrist=(0.4, 0.6), right_wrist=(0.6, 0.6),
)
UP = make_landmarks(
    nose=(0.5, 0.2),
    left_shoulder=(0.4, 0.3), right_shoulder=(0.6, 0.3),
    left_wrist=(0.4, 0.1), right_wrist=(0.6, 0.1),
)


def test_initial_count_is_zero():
    tracker = OverheadReachTracker()
    assert tracker.update(DOWN) == 0


def test_full_cycle_counts_one():
    tracker = OverheadReachTracker()
    sequence = [DOWN, DOWN, UP, UP, DOWN]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0, 0, 1]
