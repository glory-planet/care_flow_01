from angle_calculator import calculate_angle
from landmarks import get_point


class WallSlideTracker:
    label = "벽 짚고 어깨 스트레칭"
    instruction = "벽에 팔을 대고 위아래로 밀어 올리세요"

    EXTENDED_THRESHOLD = 160
    BENT_THRESHOLD = 100

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "bent"
        self.count = 0

    def update(self, landmarks):
        shoulder = get_point(landmarks, "right_shoulder")
        elbow = get_point(landmarks, "right_elbow")
        wrist = get_point(landmarks, "right_wrist")
        if shoulder is None or elbow is None or wrist is None:
            return self.count

        angle = calculate_angle(shoulder, elbow, wrist)

        if self.state == "bent" and angle > self.EXTENDED_THRESHOLD:
            self.state = "extended"
        elif self.state == "extended" and angle < self.BENT_THRESHOLD:
            self.state = "bent"
            self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
