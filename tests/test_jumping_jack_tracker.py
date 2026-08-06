from jumping_jack_tracker import JumpingJackTracker
from tests.helpers import make_landmarks

# 팔을 옆구리에 늘어뜨리고 다리를 모은 실제 휴식 자세.
# 손목은 어깨보다 아래(엉덩이 높이 근처)에 있다.
CLOSED = make_landmarks(
    left_hip=(0.45, 0.5), right_hip=(0.55, 0.5),
    left_shoulder=(0.45, 0.3), right_shoulder=(0.55, 0.3),
    left_wrist=(0.42, 0.55), right_wrist=(0.58, 0.55),
    left_ankle=(0.47, 0.9), right_ankle=(0.53, 0.9),
)
# 팔을 머리 위로 들어올리고 다리를 벌린 자세.
# 손목은 어깨보다 위에 있다.
OPEN = make_landmarks(
    left_hip=(0.45, 0.5), right_hip=(0.55, 0.5),
    left_shoulder=(0.45, 0.3), right_shoulder=(0.55, 0.3),
    left_wrist=(0.3, 0.15), right_wrist=(0.7, 0.15),
    left_ankle=(0.2, 0.9), right_ankle=(0.8, 0.9),
)


def test_initial_count_is_zero():
    tracker = JumpingJackTracker()
    assert tracker.update(CLOSED) == 0


def test_full_cycle_counts_one():
    tracker = JumpingJackTracker()
    sequence = [CLOSED, CLOSED, OPEN, OPEN, CLOSED]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 0, 0, 1]


def test_two_full_cycles_counts_two():
    tracker = JumpingJackTracker()
    sequence = [CLOSED, OPEN, CLOSED, OPEN, CLOSED]
    counts = [tracker.update(lm) for lm in sequence]
    assert counts == [0, 0, 1, 1, 2]
