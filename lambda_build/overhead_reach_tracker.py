from landmarks import get_point


class OverheadReachTracker:
    label = "만세 자세"
    instruction = "양팔을 머리 위로 쭉 뻗으세요"

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "down"
        self.count = 0

    def update(self, landmarks):
        nose = get_point(landmarks, "nose")
        left_wrist = get_point(landmarks, "left_wrist")
        right_wrist = get_point(landmarks, "right_wrist")
        left_shoulder = get_point(landmarks, "left_shoulder")
        right_shoulder = get_point(landmarks, "right_shoulder")
        if None in (nose, left_wrist, right_wrist, left_shoulder, right_shoulder):
            return self.count

        wrist_y = (left_wrist[1] + right_wrist[1]) / 2
        shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2

        if self.state == "down" and wrist_y < nose[1]:
            self.state = "up"
        elif self.state == "up" and wrist_y > shoulder_y:
            self.state = "down"
            self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
