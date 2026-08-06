from wall_slide_tracker import WallSlideTracker
from tests.helpers import make_landmarks

BENT = make_landmarks(
    right_shoulder=(0.5, 0.3), right_elbow=(0.9, 0.6), right_wrist=(0.5, 0.9)
)
EXTENDED = make_landmarks(
    right_shoulder=(0.5, 0.3), right_elbow=(0.5, 0.6), right_wrist=(0.5, 0.9)
)


def test_initial_count_is_zero():
    tracker = WallSlideTracker()
    assert tracker.update(BENT) == 0


def test_full_cycle_counts_one():
    tracker = WallSlideTracker()
    sequence = [BENT, BENT, EXTENDED, EXTENDED, BENT]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0, 0, 1]
