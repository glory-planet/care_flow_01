import json
from datetime import datetime
from unittest.mock import patch

import pytest

import dashboard.server as server_module
from dashboard.data_store import append_session, save_assignments
from dashboard.server import build_recording_filename


@pytest.fixture
def client(tmp_path, monkeypatch):
    store_path = str(tmp_path / "store.json")
    monkeypatch.setattr(server_module, "STORE_PATH", store_path)
    server_module.app.config["TESTING"] = True
    with server_module.app.test_client() as c:
        yield c, store_path


def test_get_patient_assignments_returns_assignments_with_completed_flag(client):
    c, store_path = client
    from dashboard.data_store import save_patient_assignments

    save_patient_assignments(store_path, "p1", [{"exercise_key": "1", "target_reps": 12}])
    today = datetime.now().strftime("%Y-%m-%dT00:00:00")
    append_session(store_path, {
        "session_id": "a", "exercise_key": "1", "patient_id": "p1",
        "ended_at": today, "target_reached": True,
    })

    resp = c.get("/api/patients/p1/assignments")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == [{"exercise_key": "1", "target_reps": 12, "patient_id": "p1", "completed": True}]


def test_get_patient_assignments_returns_empty_list_when_none_assigned(client):
    c, store_path = client
    save_assignments(store_path, [])

    resp = c.get("/api/patients/p1/assignments")

    assert resp.status_code == 200
    assert resp.get_json() == []


def test_start_exercise_launches_subprocess_without_blocking(client):
    c, store_path = client
    save_assignments(store_path, [{"exercise_key": "1", "target_reps": 12}])

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        resp = c.post(
            "/api/start-exercise",
            data=json.dumps({"exercise_key": "1"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "session_id" in body
        mock_popen.assert_called_once()
        called_cmd = mock_popen.call_args[0][0]
        assert "--exercise" in called_cmd
        assert "1" in called_cmd


def test_start_exercise_passes_patient_id_to_subprocess(client):
    c, store_path = client
    save_assignments(store_path, [{"exercise_key": "1", "target_reps": 12}])

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        resp = c.post(
            "/api/start-exercise",
            data=json.dumps({"exercise_key": "1", "patient_id": "p1"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        called_cmd = mock_popen.call_args[0][0]
        assert "--patient-id" in called_cmd
        assert "p1" in called_cmd


def test_start_exercise_omits_patient_id_flag_when_not_provided(client):
    c, store_path = client
    save_assignments(store_path, [{"exercise_key": "1", "target_reps": 12}])

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        c.post(
            "/api/start-exercise",
            data=json.dumps({"exercise_key": "1"}),
            content_type="application/json",
        )
        called_cmd = mock_popen.call_args[0][0]
        assert "--patient-id" not in called_cmd


def test_get_sessions_returns_newest_first(client):
    c, store_path = client

    append_session(store_path, {"session_id": "a", "exercise_key": "1", "ended_at": "2026-08-01T09:00:00"})
    append_session(store_path, {"session_id": "b", "exercise_key": "1", "ended_at": "2026-08-02T09:00:00"})

    resp = c.get("/api/sessions")
    ids = [s["session_id"] for s in resp.get_json()]
    assert ids == ["b", "a"]


def test_get_video_missing_session_returns_404(client):
    c, _ = client
    resp = c.get("/api/video/does-not-exist")
    assert resp.status_code == 404


def test_build_recording_filename_includes_patient_time_exercise_and_session():
    ts = datetime(2026, 8, 2, 9, 14, 32)
    filename = build_recording_filename("1", "abc123", timestamp=ts)
    assert filename == "홍은결_20260802_091432_스쿼트_abc123.webm"


def test_build_recording_filename_falls_back_to_key_for_unknown_exercise():
    ts = datetime(2026, 8, 2, 9, 14, 32)
    filename = build_recording_filename("99", "abc123", timestamp=ts)
    assert filename == "홍은결_20260802_091432_99_abc123.webm"


def test_stretch_reminder_status_false_when_not_started(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(server_module, "stretch_reminder_process", None)
    resp = c.get("/api/stretch-reminder/status")
    assert resp.get_json() == {"running": False}


def test_stretch_reminder_start_launches_subprocess(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(server_module, "stretch_reminder_process", None)

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        mock_popen.return_value.poll.return_value = None
        resp = c.post("/api/stretch-reminder/start")
        assert resp.get_json() == {"running": True}
        mock_popen.assert_called_once()

        status_resp = c.get("/api/stretch-reminder/status")
        assert status_resp.get_json() == {"running": True}


def test_stretch_reminder_start_does_not_relaunch_if_already_running(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(server_module, "stretch_reminder_process", None)

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        mock_popen.return_value.poll.return_value = None
        c.post("/api/stretch-reminder/start")
        c.post("/api/stretch-reminder/start")
        assert mock_popen.call_count == 1


def test_stretch_reminder_stop_terminates_running_process(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(server_module, "stretch_reminder_process", None)

    with patch.object(server_module.subprocess, "Popen") as mock_popen:
        mock_popen.return_value.poll.return_value = None
        c.post("/api/stretch-reminder/start")
        resp = c.post("/api/stretch-reminder/stop")
        assert resp.get_json() == {"running": False}
        mock_popen.return_value.terminate.assert_called_once()

        status_resp = c.get("/api/stretch-reminder/status")
        assert status_resp.get_json() == {"running": False}


def test_patient_stats_includes_attendance_rate(client):
    c, store_path = client
    from dashboard.data_store import save_patient_assignments

    save_patient_assignments(store_path, "p1", [{"exercise_key": "1", "target_reps": 12}])
    append_session(store_path, {
        "session_id": "a", "exercise_key": "1", "patient_id": "p1",
        "ended_at": "2026-08-04T09:00:00", "target_reached": True,
    })
    append_session(store_path, {
        "session_id": "b", "exercise_key": "1", "patient_id": "p1",
        "ended_at": "2026-08-03T09:00:00", "target_reached": False,
    })

    with patch("dashboard.server.date") as mock_date:
        mock_date.today.return_value = __import__("datetime").date(2026, 8, 5)
        mock_date.side_effect = lambda *a, **kw: __import__("datetime").date(*a, **kw)
        resp = c.get("/api/patients/p1/stats")

    body = resp.get_json()
    assert body["attendance"]["active_days"] == 2
    assert body["attendance"]["total_days"] == 7
    assert body["attendance"]["rate"] == round(2 / 7 * 100)
    assert "summary" in body


def test_patient_stats_summary_uses_rolling_week_not_calendar_week(client):
    """summary must reflect the rolling 7-day achievement rate, not the
    calendar-week rate — regression test for the doctor-dashboard /
    patient-detail-page disagreement bug."""
    c, store_path = client
    from dashboard.data_store import save_patient_assignments

    save_patient_assignments(store_path, "p1", [{"exercise_key": "1", "target_reps": 12}])
    # Both sessions fall in the rolling 7-day window (2026-07-30..2026-08-05)
    # but BEFORE the calendar week start (Monday 2026-08-03), so the
    # calendar-week achievement rate is 0% while the rolling rate is not.
    append_session(store_path, {
        "session_id": "a", "exercise_key": "1", "patient_id": "p1",
        "ended_at": "2026-07-30T09:00:00", "target_reached": True,
    })
    append_session(store_path, {
        "session_id": "b", "exercise_key": "1", "patient_id": "p1",
        "ended_at": "2026-07-31T09:00:00", "target_reached": False,
    })

    with patch("dashboard.server.date") as mock_date:
        mock_date.today.return_value = __import__("datetime").date(2026, 8, 5)
        mock_date.side_effect = lambda *a, **kw: __import__("datetime").date(*a, **kw)
        resp = c.get("/api/patients/p1/stats")

    body = resp.get_json()
    # Calendar week (Mon 08-03 .. Wed 08-05) has no sessions at all.
    assert body["weekly"]["rate"] == 0
    # Rolling 7-day window (07-30 .. 08-05) has 1 achieved day out of 7.
    assert body["attendance"]["achieve_rate"] == round(1 / 7 * 100)

    assert "summary" in body
    summary = body["summary"]
    # Summary must use the rolling rate (14%), not the calendar-week rate (0%).
    assert "배정 운동 달성률은 14%" in summary
    assert "배정 운동 달성률은 0%" not in summary


def test_build_stats_summary_high_achievement():
    from dashboard.server import build_stats_summary
    text = build_stats_summary(active_days=6, total_days=7, achieve_rate=90)
    assert "최근 7일 출석률 86%" in text
    assert "목표 달성이 우수합니다" in text


def test_build_stats_summary_low_achievement():
    from dashboard.server import build_stats_summary
    text = build_stats_summary(active_days=2, total_days=7, achieve_rate=30)
    assert "출석 독려가 필요합니다" in text


def test_patient_chat_returns_llm_reply_and_logs_conversation(client, monkeypatch):
    c, store_path = client
    from dashboard.data_store import load_store

    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    monkeypatch.setattr(
        "dashboard.server.generate_reply",
        lambda system_prompt, message: "화이팅입니다! 오늘도 잘 하셨어요.",
    )

    resp = c.post(
        "/api/chat",
        data=json.dumps({"message": "오늘 스쿼트 힘들어요"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"reply": "화이팅입니다! 오늘도 잘 하셨어요."}

    store = load_store(store_path)
    assert len(store["chat_logs"]) == 2
    assert store["chat_logs"][0]["role"] == "user"
    assert store["chat_logs"][0]["message"] == "오늘 스쿼트 힘들어요"
    assert store["chat_logs"][0]["patient_id"] == "p1"
    assert store["chat_logs"][1]["role"] == "bot"
    assert store["chat_logs"][1]["message"] == "화이팅입니다! 오늘도 잘 하셨어요."


def test_patient_chat_forbidden_for_non_patient(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1"],
        }

    resp = c.post(
        "/api/chat",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_patient_chat_forbidden_when_not_logged_in(client):
    c, _ = client
    resp = c.post(
        "/api/chat",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_patient_chat_returns_400_when_message_missing(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    resp = c.post("/api/chat", data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "message is required"}


def test_patient_chat_returns_400_when_message_empty(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    resp = c.post("/api/chat", data=json.dumps({"message": ""}), content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "message is required"}


def _seed_patients(store_path, patients):
    import json as _json
    with open(store_path, "r", encoding="utf-8") as f:
        store = _json.load(f)
    store["patients"] = patients
    with open(store_path, "w", encoding="utf-8") as f:
        _json.dump(store, f, ensure_ascii=False)


def test_doctor_chat_with_patient_id_scopes_context_to_that_patient(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])  # ensures store.json file exists on disk
    _seed_patients(store_path, [{"id": "p1", "name": "홍은결", "diagnosis": "무릎 재활"}])

    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1"],
        }

    captured = {}

    def fake_generate_reply(system_prompt, message):
        captured["system_prompt"] = system_prompt
        return "이 환자는 최근 잘 하고 있습니다."

    monkeypatch.setattr("dashboard.server.generate_reply", fake_generate_reply)

    resp = c.post(
        "/api/doctor/chat",
        data=json.dumps({"message": "이 환자 어때요?", "patient_id": "p1"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"reply": "이 환자는 최근 잘 하고 있습니다."}
    assert "홍은결" in captured["system_prompt"]


def test_doctor_chat_rejects_patient_not_assigned_to_this_doctor(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patients(store_path, [{"id": "p1", "name": "홍은결"}])

    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1"],
        }

    resp = c.post(
        "/api/doctor/chat",
        data=json.dumps({"message": "hi", "patient_id": "p999"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_doctor_chat_without_patient_id_summarizes_all_assigned_patients(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patients(store_path, [
        {"id": "p1", "name": "홍은결"},
        {"id": "p2", "name": "김민지"},
    ])

    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1", "p2"],
        }

    captured = {}

    def fake_generate_reply(system_prompt, message):
        captured["system_prompt"] = system_prompt
        return "두 분 모두 최근 출석은 양호합니다."

    monkeypatch.setattr("dashboard.server.generate_reply", fake_generate_reply)

    resp = c.post(
        "/api/doctor/chat",
        data=json.dumps({"message": "요즘 환자들 어때요?"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert "홍은결" in captured["system_prompt"]
    assert "김민지" in captured["system_prompt"]


def test_doctor_chat_forbidden_for_non_doctor(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    resp = c.post(
        "/api/doctor/chat",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_doctor_chat_returns_400_when_message_missing(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1"],
        }

    resp = c.post("/api/doctor/chat", data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "message is required"}


def _raise_llm_error(*args, **kwargs):
    raise RuntimeError("groq boom")


def test_patient_chat_returns_503_when_llm_fails(client, monkeypatch):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    monkeypatch.setattr("dashboard.server.generate_reply", _raise_llm_error)

    resp = c.post(
        "/api/chat",
        data=json.dumps({"message": "오늘 스쿼트 힘들어요"}),
        content_type="application/json",
    )
    assert resp.status_code == 503
    assert resp.get_json()["error"]


def test_patient_chat_does_not_log_orphan_user_turn_when_llm_fails(client, monkeypatch):
    c, store_path = client
    from dashboard.data_store import load_store

    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    monkeypatch.setattr("dashboard.server.generate_reply", _raise_llm_error)

    c.post(
        "/api/chat",
        data=json.dumps({"message": "오늘 스쿼트 힘들어요"}),
        content_type="application/json",
    )

    store = load_store(store_path)
    assert store["chat_logs"] == []


def test_patient_chat_forbidden_when_patient_id_missing(client):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": None, "patient_ids": None,
        }

    resp = c.post(
        "/api/chat",
        data=json.dumps({"message": "hi"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_doctor_chat_returns_503_when_llm_fails(client, monkeypatch):
    c, _ = client
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": ["p1"],
        }

    monkeypatch.setattr("dashboard.server.generate_reply", _raise_llm_error)

    resp = c.post(
        "/api/doctor/chat",
        data=json.dumps({"message": "이 환자 어때요?"}),
        content_type="application/json",
    )
    assert resp.status_code == 503
    assert resp.get_json()["error"]


def _login_as_doctor(c):
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": [],
        }


def test_register_patient_creates_patient_with_matching_id_and_registration_number(client):
    c, store_path = client
    save_assignments(store_path, [])
    _login_as_doctor(c)

    resp = c.post(
        "/api/patients",
        data=json.dumps({"name": "김민수", "age": 40, "diagnosis": "좌측 어깨 회전근개 부분파열", "joint": "어깨"}),
        content_type="application/json",
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "김민수"
    assert body["id"] == body["registration_number"]
    assert len(body["id"]) == 5
    assert body["id"].isdigit()

    from dashboard.data_store import get_patients
    patients = get_patients(store_path)
    assert len(patients) == 1
    assert patients[0]["id"] == body["id"]


def test_register_patient_requires_name(client):
    c, store_path = client
    save_assignments(store_path, [])
    _login_as_doctor(c)

    resp = c.post(
        "/api/patients",
        data=json.dumps({"age": 40, "diagnosis": "무릎 통증"}),
        content_type="application/json",
    )

    assert resp.status_code == 400


def test_register_patient_forbidden_for_non_doctor(client):
    c, store_path = client
    save_assignments(store_path, [])
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    resp = c.post(
        "/api/patients",
        data=json.dumps({"name": "김민수", "age": 40, "diagnosis": "무릎 통증"}),
        content_type="application/json",
    )

    assert resp.status_code == 403


def test_register_patient_forbidden_when_not_logged_in(client):
    c, store_path = client
    save_assignments(store_path, [])

    resp = c.post(
        "/api/patients",
        data=json.dumps({"name": "김민수", "age": 40, "diagnosis": "무릎 통증"}),
        content_type="application/json",
    )

    assert resp.status_code == 403


def test_hospital_lookup_returns_patient_info_when_found(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _login_as_doctor(c)

    monkeypatch.setattr(
        "dashboard.server.lookup_patient_by_unique_id",
        lambda uid: {"unique_id": uid, "name": "조하은", "age": 41, "diagnosis": "우측 어깨 회전근개 부분파열 (급성기)", "joint": "어깨"},
    )

    resp = c.get("/api/hospital-lookup/13905")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "조하은"
    assert body["diagnosis"] == "우측 어깨 회전근개 부분파열 (급성기)"


def test_hospital_lookup_returns_404_when_not_found(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _login_as_doctor(c)

    monkeypatch.setattr("dashboard.server.lookup_patient_by_unique_id", lambda uid: None)

    resp = c.get("/api/hospital-lookup/99999")

    assert resp.status_code == 404


def test_hospital_lookup_returns_503_when_backend_fails(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _login_as_doctor(c)

    def _boom(uid):
        raise RuntimeError("s3vectors down")

    monkeypatch.setattr("dashboard.server.lookup_patient_by_unique_id", _boom)

    resp = c.get("/api/hospital-lookup/13905")

    assert resp.status_code == 503


def test_hospital_lookup_forbidden_for_non_doctor(client):
    c, store_path = client
    save_assignments(store_path, [])
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "patient1", "role": "patient", "name": "환자",
            "patient_id": "p1", "patient_ids": None,
        }

    resp = c.get("/api/hospital-lookup/13905")

    assert resp.status_code == 403


def test_register_patient_adds_to_doctor_patient_ids_and_updates_session(client):
    c, store_path = client
    save_assignments(store_path, [])
    with c.session_transaction() as sess:
        sess["user"] = {
            "username": "doc1", "role": "doctor", "name": "의사",
            "patient_id": None, "patient_ids": [],
        }

    from dashboard.data_store import load_store
    store = load_store(store_path)
    store["users"] = [{"username": "doc1", "role": "doctor", "name": "의사", "patient_ids": []}]
    from dashboard.data_store import _write
    _write(store_path, store)

    resp = c.post(
        "/api/patients",
        data=json.dumps({"name": "김민수", "age": 40, "diagnosis": "무릎 통증"}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    new_id = resp.get_json()["id"]

    store = load_store(store_path)
    assert new_id in store["users"][0]["patient_ids"]

    # session's cached patient_ids should also reflect the new patient without re-login
    summary_resp = c.get("/api/doctor/patients-summary")
    assert summary_resp.status_code == 200
    summary_ids = [p["id"] for p in summary_resp.get_json()]
    assert new_id in summary_ids
