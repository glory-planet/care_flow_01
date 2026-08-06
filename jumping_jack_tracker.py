from landmarks import get_point


class JumpingJackTracker:
    label = "잭점프"
    instruction = "팔다리를 동시에 벌렸다 모으세요"

    LEG_OPEN_RATIO = 1.5
    LEG_CLOSE_RATIO = 1.2

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "closed"
        self.count = 0

    def update(self, landmarks):
        left_wrist = get_point(landmarks, "left_wrist")
        right_wrist = get_point(landmarks, "right_wrist")
        left_shoulder = get_point(landmarks, "left_shoulder")
        right_shoulder = get_point(landmarks, "right_shoulder")
        left_ankle = get_point(landmarks, "left_ankle")
        right_ankle = get_point(landmarks, "right_ankle")
        left_hip = get_point(landmarks, "left_hip")
        right_hip = get_point(landmarks, "right_hip")
        required = (
            left_wrist, right_wrist, left_shoulder, right_shoulder,
            left_ankle, right_ankle, left_hip, right_hip,
        )
        if None in required:
            return self.count

        hip_width = abs(left_hip[0] - right_hip[0])
        if hip_width == 0:
            return self.count

        shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
        wrist_y = (left_wrist[1] + right_wrist[1]) / 2
        arms_raised = wrist_y < shoulder_y

        leg_spread = abs(left_ankle[0] - right_ankle[0]) / hip_width

        is_open = arms_raised and leg_spread > self.LEG_OPEN_RATIO
        is_closed = not arms_raised and leg_spread < self.LEG_CLOSE_RATIO

        if self.state == "closed" and is_open:
            self.state = "open"
        elif self.state == "open" and is_closed:
            self.state = "closed"
            self.count += 1

        return self.count

    def display_text(self):
        return f"{self.label}: {self.count}"
