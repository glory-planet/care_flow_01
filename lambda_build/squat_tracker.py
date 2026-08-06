from angle_calculator import calculate_angle
from landmarks import get_point


class SquatTracker:
    label = "스쿼트"
    instruction = "무릎을 굽혔다 펴세요"

    STANDING_THRESHOLD = 160
    SQUATTING_THRESHOLD = 100

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "standing"
        self.count = 0

    def update(self, landmarks):
        hip = get_point(landmarks, "left_hip")
        knee = get_point(landmarks, "left_knee")
        ankle = get_point(landmarks, "left_ankle")
        if hip is None or knee is None or ankle is None:
            return self.count

        angle = calculate_angle(hip, knee, ankle)

        if self.state == "standing" and angle < self.SQUATTING_THRESHOLD:
            self.state = "squatting"
        elif self.state == "squatting" and angle > self.STANDING_THRESHOLD:
            self.state = "standing"
            self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
