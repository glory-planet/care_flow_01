from landmarks import get_point


class SideLegRaiseTracker:
    label = "사이드 레그 레이즈"
    instruction = "다리를 옆으로 들어올리세요"

    RAISE_RATIO = 1.5
    LOWER_RATIO = 1.2

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "together"
        self.count = 0

    def update(self, landmarks):
        left_ankle = get_point(landmarks, "left_ankle")
        right_ankle = get_point(landmarks, "right_ankle")
        left_hip = get_point(landmarks, "left_hip")
        right_hip = get_point(landmarks, "right_hip")
        if None in (left_ankle, right_ankle, left_hip, right_hip):
            return self.count

        hip_width = abs(left_hip[0] - right_hip[0])
        if hip_width == 0:
            return self.count

        ratio = abs(left_ankle[0] - right_ankle[0]) / hip_width

        if self.state == "together" and ratio > self.RAISE_RATIO:
            self.state = "raised"
        elif self.state == "raised" and ratio < self.LOWER_RATIO:
            self.state = "together"
            self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
