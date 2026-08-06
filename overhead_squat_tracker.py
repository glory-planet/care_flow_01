from angle_calculator import calculate_angle
from landmarks import get_point


class OverheadSquatTracker:
    label = "오버헤드 스쿼트"
    instruction = "팔을 머리 위로 든 채 스쿼트하세요"

    STANDING_THRESHOLD = 160
    SQUATTING_THRESHOLD = 100

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "standing"
        self.count = 0
        self._valid_rep = True

    def update(self, landmarks):
        hip = get_point(landmarks, "left_hip")
        knee = get_point(landmarks, "left_knee")
        ankle = get_point(landmarks, "left_ankle")
        nose = get_point(landmarks, "nose")
        left_wrist = get_point(landmarks, "left_wrist")
        right_wrist = get_point(landmarks, "right_wrist")
        if None in (hip, knee, ankle, nose, left_wrist, right_wrist):
            return self.count

        angle = calculate_angle(hip, knee, ankle)
        arms_overhead = left_wrist[1] < nose[1] and right_wrist[1] < nose[1]

        if self.state == "standing" and angle < self.SQUATTING_THRESHOLD:
            self.state = "squatting"
            self._valid_rep = arms_overhead
        elif self.state == "squatting":
            if not arms_overhead:
                self._valid_rep = False
            if angle > self.STANDING_THRESHOLD:
                self.state = "standing"
                if self._valid_rep:
                    self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
