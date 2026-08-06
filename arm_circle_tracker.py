import math

from landmarks import get_point


class ArmCircleTracker:
    label = "양팔 원 그리기"
    instruction = "오른팔을 옆으로 뻗고 크게 원을 그리세요"

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self._last_angle = None
        self._accumulated = 0.0

    def update(self, landmarks):
        shoulder = get_point(landmarks, "right_shoulder")
        wrist = get_point(landmarks, "right_wrist")
        if shoulder is None or wrist is None:
            return self.count

        angle = math.degrees(math.atan2(wrist[1] - shoulder[1], wrist[0] - shoulder[0]))

        if self._last_angle is not None:
            delta = angle - self._last_angle
            while delta > 180:
                delta -= 360
            while delta < -180:
                delta += 360
            self._accumulated += abs(delta)

            if self._accumulated >= 360:
                self.count += 1
                self._accumulated -= 360

        self._last_angle = angle
        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
