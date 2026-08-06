from landmarks import LANDMARK


def make_landmarks(**overrides):
    """테스트용 33개 관절 좌표 리스트를 만든다.

    기본값은 전부 visibility=0(안 보임)이며, overrides로 넘긴 관절만
    visibility=1.0으로 활성화된 (x, y) 좌표를 갖는다.
    예: make_landmarks(left_hip=(0.5, 0.5), left_knee=(0.5, 0.7))
    """
    landmarks = [(0.0, 0.0, 0.0, 0.0) for _ in range(33)]
    for name, (x, y) in overrides.items():
        landmarks[LANDMARK[name]] = (x, y, 0.0, 1.0)
    return landmarks
