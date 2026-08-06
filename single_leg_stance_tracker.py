import time

from landmarks import get_point


class SingleLegStanceTracker:
    label = "한 발 서기 균형"
    instruction = "한쪽 발을 들고 최대한 오래 버티세요"

    LIFT_THRESHOLD = 0.08

    def __init__(self, time_fn=time.time):
        self._time_fn = time_fn
        self.reset()

    def reset(self):
        self.balancing = False
        self.start_time = None
        self.elapsed = 0.0

    def update(self, landmarks):
        left_ankle = get_point(landmarks, "left_ankle")
        right_ankle = get_point(landmarks, "right_ankle")
        if left_ankle is None or right_ankle is None:
            return self.elapsed

        diff = abs(left_ankle[1] - right_ankle[1])

        if diff > self.LIFT_THRESHOLD:
            if not self.balancing:
                self.balancing = True
                self.start_time = self._time_fn()
            self.elapsed = self._time_fn() - self.start_time
        else:
            self.balancing = False
            self.start_time = None
            self.elapsed = 0.0

        return self.elapsed

    def display_text(self):
        return f"{self.label}: {self.elapsed:.1f}s"
