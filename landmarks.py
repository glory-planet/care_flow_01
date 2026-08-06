LANDMARK = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
}

VISIBILITY_THRESHOLD = 0.5


def get_point(landmarks, name):
    """landmarks: PoseDetector.detect()가 반환하는 33개 (x, y, z, visibility) 리스트.

    정규화된 (x, y) 좌표를 반환한다. visibility가 낮으면 None.
    """
    x, y, _z, visibility = landmarks[LANDMARK[name]]
    if visibility < VISIBILITY_THRESHOLD:
        return None
    return (x, y)
