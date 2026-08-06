import numpy as np


def calculate_angle(a, b, c):
    """세 점 a, b, c에서 b를 꼭짓점으로 하는 각도를 도 단위로 반환한다.

    a, b, c: (x, y) 형태의 좌표 (튜플, 리스트, 또는 numpy 배열).
    """
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    c = np.array(c, dtype=float)

    ba = a - b
    bc = c - b

    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)

    return float(np.degrees(np.arccos(cosine_angle)))
