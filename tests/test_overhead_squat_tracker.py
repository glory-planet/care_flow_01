from overhead_squat_tracker import OverheadSquatTracker
from tests.helpers import make_landmarks

NOSE = (0.5, 0.1)
ARMS_UP = {"left_wrist": (0.4, 0.05), "right_wrist": (0.6, 0.05)}
ARMS_DOWN = {"left_wrist": (0.4, 0.5), "right_wrist": (0.6, 0.5)}

STAND_KNEE = (0.5, 0.6)
SQUAT_KNEE = (0.9, 0.6)


def landmarks_at(knee, arms):
    return make_landmarks(
        nose=NOSE,
        left_hip=(0.5, 0.3), left_knee=knee, left_ankle=(0.5, 0.9),
        **arms,
    )


def test_valid_rep_with_arms_overhead_counts_one():
    tracker = OverheadSquatTracker()
    sequence = [
        landmarks_at(STAND_KNEE, ARMS_UP),
        landmarks_at(SQUAT_KNEE, ARMS_UP),
        landmarks_at(STAND_KNEE, ARMS_UP),
    ]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 1]


def test_arms_down_during_squat_does_not_count():
    tracker = OverheadSquatTracker()
    sequence = [
        landmarks_at(STAND_KNEE, ARMS_UP),
        landmarks_at(SQUAT_KNEE, ARMS_DOWN),
        landmarks_at(STAND_KNEE, ARMS_UP),
    ]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0]


def test_arms_drop_mid_squat_invalidates_rep():
    tracker = OverheadSquatTracker()
    sequence = [
        landmarks_at(SQUAT_KNEE, ARMS_UP),
        landmarks_at(SQUAT_KNEE, ARMS_DOWN),
        landmarks_at(STAND_KNEE, ARMS_UP),
    ]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0]
