import json
import os

from dashboard.data_store import (
    append_chat_log,
    append_session,
    clear_video_jobs,
    create_video_job,
    find_patient_by_registration,
    get_kakao_session,
    get_patient_by_kakao_id,
    get_patient_chat_logs,
    get_video_jobs,
    link_kakao_user,
    load_store,
    save_assignments,
    save_kakao_session,
    update_video_job,
)


def test_load_store_missing_file_returns_defaults(tmp_path):
    path = str(tmp_path / "store.json")
    store = load_store(path)
    assert store == {
        "users": [], "patients": [], "assignments": [], "sessions": [], "chat_logs": [],
        "kakao_sessions": {}, "video_jobs": {},
    }


def test_load_store_corrupted_json_returns_defaults(tmp_path):
    path = str(tmp_path / "store.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    store = load_store(path)
    assert store == {
        "users": [], "patients": [], "assignments": [], "sessions": [], "chat_logs": [],
        "kakao_sessions": {}, "video_jobs": {},
    }


def test_save_and_reload_assignments(tmp_path):
    path = str(tmp_path / "nested" / "store.json")
    assignments = [{"exercise_key": "1", "target_reps": 12}]
    save_assignments(path, assignments)

    store = load_store(path)
    assert store["assignments"] == assignments
    assert store["sessions"] == []


def test_append_session_preserves_existing_sessions(tmp_path):
    path = str(tmp_path / "store.json")
    append_session(path, {"session_id": "a", "exercise_key": "1"})
    append_session(path, {"session_id": "b", "exercise_key": "5"})

    store = load_store(path)
    assert [s["session_id"] for s in store["sessions"]] == ["a", "b"]


def test_saved_file_is_valid_json_on_disk(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [{"exercise_key": "1", "target_reps": 12}])

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["assignments"][0]["exercise_key"] == "1"


def test_append_chat_log_and_filter_by_patient(tmp_path):
    path = str(tmp_path / "store.json")
    append_chat_log(path, {
        "patient_id": "p1", "channel": "web", "role": "user",
        "message": "안녕", "timestamp": "2026-08-05T09:00:00",
    })
    append_chat_log(path, {
        "patient_id": "p1", "channel": "web", "role": "bot",
        "message": "안녕하세요!", "timestamp": "2026-08-05T09:00:05",
    })
    append_chat_log(path, {
        "patient_id": "p2", "channel": "web", "role": "user",
        "message": "다른 환자", "timestamp": "2026-08-05T09:01:00",
    })

    logs = get_patient_chat_logs(path, "p1")
    assert [l["message"] for l in logs] == ["안녕", "안녕하세요!"]


def test_get_patient_chat_logs_respects_limit(tmp_path):
    path = str(tmp_path / "store.json")
    for i in range(5):
        append_chat_log(path, {
            "patient_id": "p1", "channel": "web", "role": "user",
            "message": f"msg{i}", "timestamp": f"2026-08-05T09:0{i}:00",
        })

    logs = get_patient_chat_logs(path, "p1", limit=2)
    assert [l["message"] for l in logs] == ["msg3", "msg4"]


def test_get_patient_chat_logs_limit_zero_returns_empty_list(tmp_path):
    path = str(tmp_path / "store.json")
    append_chat_log(path, {
        "patient_id": "p1", "channel": "web", "role": "user",
        "message": "hello", "timestamp": "2026-08-05T09:00:00",
    })

    logs = get_patient_chat_logs(path, "p1", limit=0)
    assert logs == []


def _seed_patient(store_path, **overrides):
    import json as _json
    patient = {
        "id": "p1", "name": "홍은결", "registration_number": "4821", "kakao_user_id": None,
    }
    patient.update(overrides)
    with open(store_path, "r", encoding="utf-8") as f:
        store = _json.load(f)
    store["patients"] = [patient]
    with open(store_path, "w", encoding="utf-8") as f:
        _json.dump(store, f, ensure_ascii=False)


def test_find_patient_by_registration_matches_name_and_number(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    _seed_patient(path)

    found = find_patient_by_registration(path, "홍은결", "4821")
    assert found["id"] == "p1"


def test_find_patient_by_registration_returns_none_when_number_wrong(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    _seed_patient(path)

    assert find_patient_by_registration(path, "홍은결", "9999") is None


def test_link_kakao_user_sets_id_and_is_findable(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    _seed_patient(path)

    link_kakao_user(path, "p1", "kakao-abc")

    found = get_patient_by_kakao_id(path, "kakao-abc")
    assert found["id"] == "p1"


def test_link_kakao_user_unlinks_previous_owner_of_same_kakao_id(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    import json as _json
    with open(path, "r", encoding="utf-8") as f:
        store = _json.load(f)
    store["patients"] = [
        {"id": "p1", "name": "홍은결", "registration_number": "4821", "kakao_user_id": "kakao-abc"},
        {"id": "p2", "name": "박서준", "registration_number": "1936", "kakao_user_id": None},
    ]
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(store, f, ensure_ascii=False)

    link_kakao_user(path, "p2", "kakao-abc")

    found = get_patient_by_kakao_id(path, "kakao-abc")
    assert found["id"] == "p2"


def test_get_kakao_session_defaults_to_idle_state(tmp_path):
    path = str(tmp_path / "store.json")
    assert get_kakao_session(path, "kakao-abc") == {"state": "idle"}


def test_save_and_reload_kakao_session(tmp_path):
    path = str(tmp_path / "store.json")
    save_kakao_session(path, "kakao-abc", {"state": "survey_pre", "step": 1})

    assert get_kakao_session(path, "kakao-abc") == {"state": "survey_pre", "step": 1}


def test_create_video_job_returns_job_id_and_stores_pending_status(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])

    job_id = create_video_job(path, "kakao-abc", "1", 12)

    jobs = get_video_jobs(path, "kakao-abc")
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id
    assert jobs[0]["exercise_key"] == "1"
    assert jobs[0]["target_reps"] == 12
    assert jobs[0]["status"] == "pending"
    assert jobs[0]["pose_detected"] is None
    assert jobs[0]["final_value"] is None


def test_create_video_job_appends_multiple_jobs_for_same_user(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])

    create_video_job(path, "kakao-abc", "1", 12)
    create_video_job(path, "kakao-abc", "2", 10)

    jobs = get_video_jobs(path, "kakao-abc")
    assert len(jobs) == 2


def test_update_video_job_sets_fields_by_job_id(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    job_id = create_video_job(path, "kakao-abc", "1", 12)

    update_video_job(path, "kakao-abc", job_id, status="done", pose_detected=True, final_value=14)

    jobs = get_video_jobs(path, "kakao-abc")
    assert jobs[0]["status"] == "done"
    assert jobs[0]["pose_detected"] is True
    assert jobs[0]["final_value"] == 14


def test_get_video_jobs_returns_empty_list_for_unknown_user(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])

    assert get_video_jobs(path, "kakao-nobody") == []


def test_clear_video_jobs_removes_all_jobs_for_user(tmp_path):
    path = str(tmp_path / "store.json")
    save_assignments(path, [])
    create_video_job(path, "kakao-abc", "1", 12)

    clear_video_jobs(path, "kakao-abc")

    assert get_video_jobs(path, "kakao-abc") == []
