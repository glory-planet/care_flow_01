from main import build_session_record, get_tracker_value, parse_args


class FakeCountTracker:
    count = 7


class FakeDurationTracker:
    elapsed = 4.2


def test_get_tracker_value_uses_count_by_default():
    assert get_tracker_value(FakeCountTracker()) == 7


def test_get_tracker_value_uses_elapsed_when_present():
    assert get_tracker_value(FakeDurationTracker()) == 4.2


def test_parse_args_defaults_have_no_exercise():
    args = parse_args([])
    assert args.exercise is None
    assert args.target_reps is None
    assert args.output is None
    assert args.session_id is None


def test_parse_args_reads_all_flags():
    args = parse_args([
        "--exercise", "5",
        "--target-reps", "10",
        "--output", "out.mp4",
        "--session-id", "abc123",
        "--store", "custom_store.json",
        "--patient-id", "p1",
    ])
    assert args.exercise == "5"
    assert args.target_reps == 10.0
    assert args.output == "out.mp4"
    assert args.session_id == "abc123"
    assert args.store == "custom_store.json"
    assert args.patient_id == "p1"


def test_parse_args_defaults_have_no_patient_id():
    args = parse_args([])
    assert args.patient_id is None


def test_build_session_record_marks_target_reached():
    record = build_session_record(
        session_id="abc123",
        exercise_key="1",
        started_at="2026-08-02T09:00:00",
        ended_at="2026-08-02T09:05:00",
        video_path="out.mp4",
        final_value=14,
        target_reps=12,
        patient_id="p1",
    )
    assert record == {
        "session_id": "abc123",
        "exercise_key": "1",
        "started_at": "2026-08-02T09:00:00",
        "ended_at": "2026-08-02T09:05:00",
        "video_path": "out.mp4",
        "final_count": 14,
        "target_reached": True,
        "patient_id": "p1",
        "source": "webcam",
    }


def test_build_session_record_defaults_patient_id_to_none():
    record = build_session_record(
        session_id="abc123", exercise_key="1",
        started_at="t0", ended_at="t1", video_path="out.mp4",
        final_value=8, target_reps=12,
    )
    assert record["patient_id"] is None
    assert record["source"] == "webcam"


def test_build_session_record_target_not_reached():
    record = build_session_record(
        session_id="abc123", exercise_key="1",
        started_at="t0", ended_at="t1", video_path="out.mp4",
        final_value=8, target_reps=12,
    )
    assert record["target_reached"] is False


def test_build_session_record_no_target_means_not_reached():
    record = build_session_record(
        session_id="abc123", exercise_key="1",
        started_at="t0", ended_at="t1", video_path="out.mp4",
        final_value=8, target_reps=None,
    )
    assert record["target_reached"] is False
