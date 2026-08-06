import json

import pytest

import dashboard.server as server_module
from dashboard.data_store import get_kakao_session, load_store, save_assignments, save_patient_assignments


@pytest.fixture
def client(tmp_path, monkeypatch):
    store_path = str(tmp_path / "store.json")
    monkeypatch.setattr(server_module, "STORE_PATH", store_path)
    server_module.app.config["TESTING"] = True
    with server_module.app.test_client() as c:
        yield c, store_path


def _seed_patient(store_path, **overrides):
    patient = {
        "id": "52445", "name": "홍은결", "registration_number": "52445", "kakao_user_id": None,
    }
    patient.update(overrides)
    with open(store_path, "r", encoding="utf-8") as f:
        store = json.load(f)
    store["patients"] = [patient]
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)


def _kakao_payload(kakao_user_id, utterance, callback_url=None):
    user_request = {
        "utterance": utterance,
        "user": {"id": kakao_user_id},
    }
    if callback_url:
        user_request["callbackUrl"] = callback_url
    return {"userRequest": user_request}


def _post_skill(c, kakao_user_id, utterance, callback_url=None):
    resp = c.post(
        "/kakao/skill",
        data=json.dumps(_kakao_payload(kakao_user_id, utterance, callback_url)),
        content_type="application/json",
    )
    return resp.get_json()


def _video_payload(kakao_user_id, video_url, callback_url="https://bot-api.kakao.com/v1/bots/x/callback/cbtoken:abc"):
    return {
        "userRequest": {
            "utterance": video_url,
            "user": {"id": kakao_user_id},
            "params": {"media": {"type": "video", "url": video_url}},
            "callbackUrl": callback_url,
        },
        "flow": {"trigger": {"type": "IMAGE_UPLOAD"}},
    }


def _post_video(c, kakao_user_id, video_url="https://talk.kakaocdn.net/dna/fake/video.mp4", callback_url=None):
    payload = _video_payload(kakao_user_id, video_url, callback_url) if callback_url else _video_payload(kakao_user_id, video_url)
    resp = c.post("/kakao/skill", data=json.dumps(payload), content_type="application/json")
    return resp.get_json()


def _simple_text(body):
    return body["template"]["outputs"][0]["simpleText"]["text"]


# --- 신원확인 ---

def test_unrecognized_user_gets_identity_verification_prompt(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path)

    body = _post_skill(c, "kakao-new-user", "안녕하세요")

    assert "이름 등록번호" in _simple_text(body)


def test_correct_name_and_registration_number_links_kakao_user(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path)

    body = _post_skill(c, "kakao-abc", "홍은결 52445")

    assert "확인됐어요" in _simple_text(body)
    store = load_store(store_path)
    assert store["patients"][0]["kakao_user_id"] == "kakao-abc"


def test_wrong_registration_number_is_rejected(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path)

    body = _post_skill(c, "kakao-abc", "홍은결 99999")

    assert "찾을 수 없어요" in _simple_text(body)
    store = load_store(store_path)
    assert store["patients"][0]["kakao_user_id"] is None


# --- 일반 대화 ---

def test_verified_user_general_chat_calls_generate_reply_and_logs(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    monkeypatch.setattr(
        "dashboard.kakao_skill.generate_reply",
        lambda system_prompt, message: "화이팅입니다!",
    )

    body = _post_skill(c, "kakao-abc", "오늘 어깨가 좀 아파요")

    assert _simple_text(body) == "화이팅입니다!"
    store = load_store(store_path)
    assert len(store["chat_logs"]) == 2
    assert store["chat_logs"][0]["channel"] == "kakao"
    assert store["chat_logs"][0]["patient_id"] == "52445"
    assert store["chat_logs"][0]["message"] == "오늘 어깨가 좀 아파요"
    assert store["chat_logs"][1]["message"] == "화이팅입니다!"


def test_general_chat_llm_failure_returns_friendly_message(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    def _boom(*a, **kw):
        raise RuntimeError("bedrock down")

    monkeypatch.setattr("dashboard.kakao_skill.generate_reply", _boom)

    body = _post_skill(c, "kakao-abc", "안녕")

    assert "죄송해요" in _simple_text(body)


# --- 운동 전 문진 ---

def test_exercise_start_triggers_pre_survey_first_question(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    body = _post_skill(c, "kakao-abc", "운동 시작할게요")

    assert "컨디션" in _simple_text(body)


def test_full_pre_survey_flow_then_shows_exercise_list(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    _post_skill(c, "kakao-abc", "운동 시작")
    _post_skill(c, "kakao-abc", "8")
    _post_skill(c, "kakao-abc", "2")
    body = _post_skill(c, "kakao-abc", "3")

    text = _simple_text(body)
    assert "스쿼트" in text
    assert "12회" in text

    store = load_store(store_path)
    survey_logs = [c for c in store["chat_logs"] if c.get("type") == "survey"]
    assert len(survey_logs) == 1
    assert survey_logs[0]["phase"] == "pre"
    assert survey_logs[0]["answers"] == {"condition": "8", "pain": "2", "sleep": "3"}

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "exercising"


def test_survey_rejects_non_scale_answer_and_repeats_question(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    _post_skill(c, "kakao-abc", "운동 시작")
    body = _post_skill(c, "kakao-abc", "좋음")  # not a 1-10 number

    text = _simple_text(body)
    assert "1~10 사이 숫자로 다시 답해주세요" in text
    assert "컨디션" in text


def test_survey_rejects_out_of_range_scale_answer(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    _post_skill(c, "kakao-abc", "운동 시작")
    body = _post_skill(c, "kakao-abc", "11")  # out of 1-10 range

    assert "1~10 사이 숫자로 다시 답해주세요" in _simple_text(body)


def test_survey_valid_answer_after_rejection_proceeds(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    _post_skill(c, "kakao-abc", "운동 시작")
    _post_skill(c, "kakao-abc", "좋음")  # rejected
    body = _post_skill(c, "kakao-abc", "5")  # valid, should move to next question

    assert "통증" in _simple_text(body)


def test_survey_in_progress_does_not_fall_through_to_general_chat(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    called = {"count": 0}

    def _track(*a, **kw):
        called["count"] += 1
        return "이건 호출되면 안 됨"

    monkeypatch.setattr("dashboard.kakao_skill.generate_reply", _track)

    _post_skill(c, "kakao-abc", "운동 시작")
    _post_skill(c, "kakao-abc", "5")  # mid-survey answer, not general chat

    assert called["count"] == 0


def test_missing_kakao_user_id_returns_safe_message(client):
    c, store_path = client
    save_assignments(store_path, [])

    resp = c.post(
        "/kakao/skill",
        data=json.dumps({"userRequest": {"utterance": "hi", "user": {}}}),
        content_type="application/json",
    )
    body = resp.get_json()
    assert "확인할 수 없어요" in _simple_text(body)


# --- 운동 진행: 영상 없이 텍스트로 완료, 영상으로 완료(백그라운드 분석) ---

def _start_pre_survey_and_finish(c, kakao_user_id="kakao-abc"):
    _post_skill(c, kakao_user_id, "운동 시작")
    _post_skill(c, kakao_user_id, "8")
    _post_skill(c, kakao_user_id, "2")
    _post_skill(c, kakao_user_id, "3")


def test_exercise_completed_via_text_records_session_without_video_and_advances(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [
        {"exercise_key": "1", "target_reps": 12},
        {"exercise_key": "2", "target_reps": 10},
    ])
    _start_pre_survey_and_finish(c)

    body = _post_skill(c, "kakao-abc", "했어요")

    text = _simple_text(body)
    assert "완료로 기록했어요" in text
    assert "양팔원그리기" in text  # next exercise name

    store = load_store(store_path)
    assert len(store["sessions"]) == 1
    session = store["sessions"][0]
    assert session["patient_id"] == "52445"
    assert session["exercise_key"] == "1"
    assert session["source"] == "kakao_manual"
    assert session["video_path"] is None
    assert session["final_count"] is None


def test_exercise_video_upload_does_not_block_and_advances_immediately(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [
        {"exercise_key": "1", "target_reps": 12},
        {"exercise_key": "2", "target_reps": 10},
    ])
    _start_pre_survey_and_finish(c)

    started = {"count": 0}
    monkeypatch.setattr(
        "dashboard.kakao_skill._start_background",
        lambda fn, *a: started.__setitem__("count", started["count"] + 1),
    )

    body = _post_video(c, "kakao-abc")

    text = _simple_text(body)
    assert "영상 잘 받았어요" in text
    assert "양팔원그리기" in text  # advanced immediately, did not wait for analysis
    assert started["count"] == 1  # background job was kicked off, not run inline

    # No session recorded yet — analysis hasn't actually run (it's mocked as a no-op)
    store = load_store(store_path)
    assert store["sessions"] == []


def test_completing_all_exercises_moves_to_post_survey(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])
    _start_pre_survey_and_finish(c)

    body = _post_skill(c, "kakao-abc", "했어요")

    text = _simple_text(body)
    assert "모두 확인했어요" in text
    assert "불편감" in text

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "survey_post"


# --- 운동 후 문진 완료 시점: 분석 결과 종합 ---

def _finish_all_exercises_via_text(c, store_path, kakao_user_id="kakao-abc", num_exercises=1):
    _start_pre_survey_and_finish(c, kakao_user_id)
    for _ in range(num_exercises):
        _post_skill(c, kakao_user_id, "했어요")


def _complete_post_survey(c, kakao_user_id="kakao-abc", callback_url=None):
    _post_skill(c, kakao_user_id, "1")
    _post_skill(c, kakao_user_id, "2")
    return _post_skill(c, kakao_user_id, "특별한 건 없어요", callback_url=callback_url)


def test_post_survey_completes_immediately_when_no_video_jobs_pending(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])
    _finish_all_exercises_via_text(c, store_path)

    body = _complete_post_survey(c)

    assert "정말 잘 하셨어요" in _simple_text(body)

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "idle"


def test_post_survey_with_completed_video_job_shows_summary_and_records_session(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")  # job created but never analyzed (background is a no-op)

    from dashboard.data_store import get_video_jobs, update_video_job
    jobs = get_video_jobs(store_path, "kakao-abc")
    update_video_job(store_path, "kakao-abc", jobs[0]["job_id"], status="done", pose_detected=True, final_value=14)

    body = _complete_post_survey(c)

    text = _simple_text(body)
    assert "스쿼트" in text
    assert "14회" in text
    assert "달성" in text

    store = load_store(store_path)
    assert len(store["sessions"]) == 1
    assert store["sessions"][0]["final_count"] == 14
    assert store["sessions"][0]["source"] == "kakao_video"

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "idle"


def test_post_survey_with_undetected_video_job_starts_reshoot_flow(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")

    from dashboard.data_store import get_video_jobs, update_video_job
    jobs = get_video_jobs(store_path, "kakao-abc")
    update_video_job(store_path, "kakao-abc", jobs[0]["job_id"], status="done", pose_detected=False, final_value=None)

    body = _complete_post_survey(c)

    text = _simple_text(body)
    assert "잘 인식되지 않았어요" in text
    assert "스쿼트" in text

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "reshooting"
    assert session_state["queue"] == ["1"]


def test_post_survey_with_pending_job_and_no_callback_asks_user_to_check_back(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")  # job stays pending forever (background mocked as no-op)

    # complete post-survey WITHOUT a callbackUrl in the final message
    _post_skill(c, "kakao-abc", "1")
    _post_skill(c, "kakao-abc", "2")
    body = _post_skill(c, "kakao-abc", "없음")

    assert "잠시 후 아무 메시지나" in _simple_text(body)

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "awaiting_results"


def test_post_survey_with_pending_job_and_callback_returns_ack_then_waits_and_calls_back(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    # 영상 분석 자체는 배경에서 안 도는 것으로 둬서(no-op) job이 pending으로 남게 한다.
    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")

    body = _post_skill(c, "kakao-abc", "1")
    _post_skill(c, "kakao-abc", "2")
    body = _post_skill(
        c, "kakao-abc", "없음",
        callback_url="https://bot-api.kakao.com/v1/bots/x/callback/cbtoken:final",
    )

    # 문진이 끝났지만 job이 아직 pending -> useCallback ack를 즉시 반환해야 한다.
    assert body["useCallback"] is True

    # 이제 "대기 후 콜백" 함수를 직접 실행해서(진짜 스레드/sleep 없이) 콜백이 올바르게 전송되는지 확인한다.
    from dashboard.data_store import get_video_jobs, update_video_job
    from dashboard.kakao_skill import _wait_for_jobs_then_callback

    jobs = get_video_jobs(store_path, "kakao-abc")
    update_video_job(store_path, "kakao-abc", jobs[0]["job_id"], status="done", pose_detected=True, final_value=12)

    captured = {}
    monkeypatch.setattr("dashboard.kakao_skill._send_callback", lambda url, text: captured.setdefault("text", text))
    monkeypatch.setattr("dashboard.kakao_skill.time.sleep", lambda seconds: None)

    _wait_for_jobs_then_callback(store_path, "kakao-abc", "https://bot-api.kakao.com/v1/bots/x/callback/cbtoken:final")

    assert "12회" in captured["text"]
    assert "달성" in captured["text"]


def test_asking_for_results_while_still_pending_tells_user_to_wait(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")
    _post_skill(c, "kakao-abc", "1")
    _post_skill(c, "kakao-abc", "2")
    _post_skill(c, "kakao-abc", "없음")  # no callbackUrl -> awaiting_results, job still pending

    body = _post_skill(c, "kakao-abc", "다 됐나요?")

    assert "아직 영상 분석이 진행 중" in _simple_text(body)


# --- 재촬영 흐름 ---

def test_reshoot_video_success_advances_and_finishes(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")

    from dashboard.data_store import get_video_jobs, update_video_job
    jobs = get_video_jobs(store_path, "kakao-abc")
    update_video_job(store_path, "kakao-abc", jobs[0]["job_id"], status="done", pose_detected=False, final_value=None)
    _complete_post_survey(c)  # moves into reshooting state

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: fn(*a))
    monkeypatch.setattr("dashboard.kakao_skill.download_video", lambda url, path: path)
    monkeypatch.setattr(
        "dashboard.kakao_skill.analyze_video",
        lambda path, key: {"pose_detected": True, "final_value": 13},
    )
    monkeypatch.setattr("dashboard.kakao_skill.delete_video_file", lambda path: None)

    captured = {}
    monkeypatch.setattr("dashboard.kakao_skill._send_callback", lambda url, text: captured.setdefault("text", text))

    ack = _post_video(c, "kakao-abc", callback_url="https://bot-api.kakao.com/v1/bots/x/callback/cbtoken:reshoot")
    assert ack["useCallback"] is True
    assert "13회" in captured["text"]
    assert "정리했어요" in captured["text"]

    store = load_store(store_path)
    assert len(store["sessions"]) == 1
    assert store["sessions"][0]["final_count"] == 13

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "idle"


def test_reshoot_text_give_up_skips_and_finishes(client, monkeypatch):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")
    save_patient_assignments(store_path, "52445", [{"exercise_key": "1", "target_reps": 12}])

    monkeypatch.setattr("dashboard.kakao_skill._start_background", lambda fn, *a: None)
    _start_pre_survey_and_finish(c)
    _post_video(c, "kakao-abc")

    from dashboard.data_store import get_video_jobs, update_video_job
    jobs = get_video_jobs(store_path, "kakao-abc")
    update_video_job(store_path, "kakao-abc", jobs[0]["job_id"], status="done", pose_detected=False, final_value=None)
    _complete_post_survey(c)  # moves into reshooting state

    body = _post_skill(c, "kakao-abc", "어려워요")

    assert "정리했어요" in _simple_text(body)

    session_state = get_kakao_session(store_path, "kakao-abc")
    assert session_state["state"] == "idle"


def test_video_upload_outside_exercising_or_reshooting_is_rejected(client):
    c, store_path = client
    save_assignments(store_path, [])
    _seed_patient(store_path, kakao_user_id="kakao-abc")

    body = _post_video(c, "kakao-abc")

    assert "운동 시작" in _simple_text(body)
