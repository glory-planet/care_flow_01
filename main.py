import argparse
from datetime import datetime, timezone

import cv2

from angle_calculator import calculate_angle
from arm_circle_tracker import ArmCircleTracker
from dashboard.data_store import DEFAULT_STORE_PATH, append_session
from display_utils import get_screen_size, scale_to_fit
from jumping_jack_tracker import JumpingJackTracker
from landmarks import LANDMARK, VISIBILITY_THRESHOLD
from overhead_reach_tracker import OverheadReachTracker
from overhead_squat_tracker import OverheadSquatTracker
from pose_detector import PoseDetector
from side_leg_raise_tracker import SideLegRaiseTracker
from single_leg_stance_tracker import SingleLegStanceTracker
from squat_tracker import SquatTracker
from wall_slide_tracker import WallSlideTracker

SETUP_GUIDE = "Setup: stand 2-3m from camera, face forward, full body visible"
WINDOW_NAME = "Pose Detection Prototype"

POSE_CONNECTIONS = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
]


def get_pixel_point(landmarks, name, frame_width, frame_height):
    x, y, _z, visibility = landmarks[LANDMARK[name]]
    if visibility < VISIBILITY_THRESHOLD:
        return None
    return (x * frame_width, y * frame_height)


def draw_skeleton(frame, landmarks, frame_width, frame_height):
    for start_name, end_name in POSE_CONNECTIONS:
        start = get_pixel_point(landmarks, start_name, frame_width, frame_height)
        end = get_pixel_point(landmarks, end_name, frame_width, frame_height)
        if start and end:
            cv2.line(
                frame,
                (int(start[0]), int(start[1])),
                (int(end[0]), int(end[1])),
                (0, 255, 0),
                2,
            )
    for name in LANDMARK:
        point = get_pixel_point(landmarks, name, frame_width, frame_height)
        if point:
            cv2.circle(frame, (int(point[0]), int(point[1])), 4, (0, 0, 255), -1)


def draw_angle(frame, landmarks, label, a_name, b_name, c_name, frame_width, frame_height):
    a = get_pixel_point(landmarks, a_name, frame_width, frame_height)
    b = get_pixel_point(landmarks, b_name, frame_width, frame_height)
    c = get_pixel_point(landmarks, c_name, frame_width, frame_height)
    if a is None or b is None or c is None:
        return None
    angle = calculate_angle(a, b, c)
    cv2.putText(
        frame,
        f"{label}: {int(angle)}",
        (int(b[0]) + 10, int(b[1])),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 0),
        2,
    )
    return angle


def build_trackers():
    return {
        "1": SquatTracker(),
        "2": ArmCircleTracker(),
        "3": WallSlideTracker(),
        "4": OverheadReachTracker(),
        "5": SideLegRaiseTracker(),
        "6": SingleLegStanceTracker(),
        "7": OverheadSquatTracker(),
        "8": JumpingJackTracker(),
    }


def get_tracker_value(tracker):
    if hasattr(tracker, "elapsed"):
        return tracker.elapsed
    return tracker.count


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--exercise", choices=[str(i) for i in range(1, 9)], default=None)
    parser.add_argument("--target-reps", type=float, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--store", default=DEFAULT_STORE_PATH)
    parser.add_argument("--patient-id", default=None)
    return parser.parse_args(argv)


def build_session_record(session_id, exercise_key, started_at, ended_at, video_path, final_value, target_reps, patient_id=None):
    return {
        "session_id": session_id,
        "exercise_key": exercise_key,
        "started_at": started_at,
        "ended_at": ended_at,
        "video_path": video_path,
        "final_count": final_value,
        "target_reached": target_reps is not None and final_value >= target_reps,
        "patient_id": patient_id,
        "source": "webcam",
    }


def main():
    args = parse_args()
    locked = args.exercise is not None

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("웹캠을 열 수 없습니다. 다른 프로그램이 웹캠을 사용 중인지 확인하세요.")

    detector = PoseDetector()
    trackers = build_trackers()
    active_key = args.exercise if locked else "1"
    screen_width, screen_height = get_screen_size()
    initial_width = int(screen_width * 0.8)
    initial_height = int(screen_height * 0.8)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, initial_width, initial_height)

    video_writer = None
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            frame_height, frame_width = frame.shape[:2]

            if args.output and video_writer is None:
                fourcc = cv2.VideoWriter_fourcc(*"VP80")
                video_writer = cv2.VideoWriter(args.output, fourcc, 20.0, (frame_width, frame_height))

            landmarks = detector.detect(frame)

            cv2.putText(frame, SETUP_GUIDE, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            active_tracker = trackers[active_key]
            cv2.putText(
                frame,
                f"{active_key}.{active_tracker.label}: {active_tracker.instruction}",
                (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )

            if landmarks is None:
                cv2.putText(frame, "no pose detected", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            else:
                draw_skeleton(frame, landmarks, frame_width, frame_height)
                draw_angle(frame, landmarks, "L-elbow", "left_shoulder", "left_elbow", "left_wrist", frame_width, frame_height)
                draw_angle(frame, landmarks, "R-elbow", "right_shoulder", "right_elbow", "right_wrist", frame_width, frame_height)
                draw_angle(frame, landmarks, "L-knee", "left_hip", "left_knee", "left_ankle", frame_width, frame_height)
                draw_angle(frame, landmarks, "R-knee", "right_hip", "right_knee", "right_ankle", frame_width, frame_height)

                active_tracker.update(landmarks)
                cv2.putText(frame, active_tracker.display_text(), (10, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            if video_writer is not None:
                video_writer.write(frame)

            _, _, window_width, window_height = cv2.getWindowImageRect(WINDOW_NAME)
            cv2.imshow(WINDOW_NAME, scale_to_fit(frame, window_width, window_height))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if not locked:
                key_char = chr(key) if key < 256 else ""
                if key_char in trackers and key_char != active_key:
                    active_key = key_char
                    trackers[active_key].reset()
    finally:
        cap.release()
        detector.close()
        if video_writer is not None:
            video_writer.release()
        cv2.destroyAllWindows()

        if args.session_id:
            record = build_session_record(
                session_id=args.session_id,
                exercise_key=active_key,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc).isoformat(),
                video_path=args.output,
                final_value=get_tracker_value(trackers[active_key]),
                target_reps=args.target_reps,
                patient_id=args.patient_id,
            )
            append_session(args.store, record)


if __name__ == "__main__":
    main()
