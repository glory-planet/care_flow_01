from side_leg_raise_tracker import SideLegRaiseTracker
from tests.helpers import make_landmarks

TOGETHER = make_landmarks(
    left_hip=(0.45, 0.5), right_hip=(0.55, 0.5),
    left_ankle=(0.45, 0.9), right_ankle=(0.55, 0.9),
)
RAISED = make_landmarks(
    left_hip=(0.45, 0.5), right_hip=(0.55, 0.5),
    left_ankle=(0.3, 0.9), right_ankle=(0.55, 0.9),
)


def test_initial_count_is_zero():
    tracker = SideLegRaiseTracker()
    assert tracker.update(TOGETHER) == 0


def test_full_cycle_counts_one():
    tracker = SideLegRaiseTracker()
    sequence = [TOGETHER, TOGETHER, RAISED, RAISED, TOGETHER]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0, 0, 1]
