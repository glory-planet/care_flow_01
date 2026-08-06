import pytest
from single_leg_stance_tracker import SingleLegStanceTracker
from tests.helpers import make_landmarks

LIFTED = make_landmarks(left_ankle=(0.4, 0.9), right_ankle=(0.6, 0.7))
LEVEL = make_landmarks(left_ankle=(0.4, 0.8), right_ankle=(0.6, 0.8))


def test_initial_elapsed_is_zero():
    tracker = SingleLegStanceTracker(time_fn=lambda: 0.0)
    assert tracker.update(LEVEL) == 0.0


def test_elapsed_increases_while_lifted():
    clock = [10.0]
    tracker = SingleLegStanceTracker(time_fn=lambda: clock[0])

    first = tracker.update(LIFTED)
    assert first == pytest.approx(0.0)

    clock[0] = 12.5
    second = tracker.update(LIFTED)
    assert second == pytest.approx(2.5)


def test_resets_when_feet_level_again():
    clock = [0.0]
    tracker = SingleLegStanceTracker(time_fn=lambda: clock[0])

    tracker.update(LIFTED)
    clock[0] = 3.0
    tracker.update(LIFTED)

    result = tracker.update(LEVEL)
    assert result == 0.0


def test_display_text_format():
    clock = [0.0]
    tracker = SingleLegStanceTracker(time_fn=lambda: clock[0])
    tracker.update(LIFTED)
    clock[0] = 4.2
    tracker.update(LIFTED)
    assert tracker.display_text() == "한 발 서기 균형: 4.2s"
