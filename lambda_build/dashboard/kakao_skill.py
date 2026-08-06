"""카카오 오픈빌더 스킬 서버 로직.

폴백 블록이 "스킬 데이터로 봇 응답 사용"으로 설정돼 있어서, 오픈빌더 시나리오에
걸리지 않는 모든 발화가 이 모듈로 넘어온다. 즉 신원확인/일반 대화/운동 전후
문진/영상 접수·분석을 전부 이 스킬 서버 하나에서 상태머신으로 처리한다.

상태는 카카오 사용자 ID별로 kakao_sessions에 저장된다:
- idle: 기본 상태 (일반 대화 또는 트리거 발화 대기)
- survey_pre / survey_post: 운동 전/후 문진 진행 중 (step으로 문항 위치 추적)
- exercising: 문진 완료 후 배정 운동을 순서대로 촬영해서 보내는 중
  (assignments 스냅샷 + current_index로 "지금 몇 번째 운동을 기다리는지" 추적)
- awaiting_results: 운동 후 문진까지 끝났지만 영상 분석이 아직 안 끝난 상태
- reshooting: 분석 결과 포즈가 인식되지 않은 운동들을 재촬영받는 중

영상 처리 설계 (2026-08-06 재설계 — "운동 하나마다 분석 기다렸다 다음 운동" 방식은
너무 느려서 폐기):
- 영상이 도착하면 분석을 기다리지 않고 백그라운드 스레드로 넘긴 뒤 즉시 다음 운동을
  안내한다. 영상 없이 "했어요" 같은 텍스트만 보내도 영상 없는 완료 기록만 남기고
  다음 운동으로 넘어간다 (환자가 매번 영상을 보낼 필요는 없음).
- 배정된 운동을 다 확인하면 자동으로 운동 후 문진으로 넘어간다 — 이 문진에 답하는
  시간이 백그라운드 분석이 끝날 자연스러운 버퍼가 된다.
- 문진이 끝난 시점에 아직 분석 중인 영상이 있으면, 카카오 콜백(요청에 포함된
  `userRequest.callbackUrl`, 5분/1회 유효 — 카카오 공식 문서 기준)으로 완료될 때까지
  기다렸다가 결과를 전달한다. 문진 끝났을 때 이미 다 끝나 있으면 바로 요약해서 응답.
- 재촬영 판단 기준(설계 확정): 포즈가 한 번도 인식되지 않은 영상만 재촬영 대상.
  목표 횟수 미달은 재촬영 사유가 아니고 `target_reached: false`로 기록만 하고 넘어간다.
"""

import json
import os
import re
import tempfile
import threading
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

from dashboard.data_store import (
    append_chat_log,
    append_session,
    clear_video_jobs,
    create_video_job,
    find_patient_by_registration,
    get_kakao_session,
    get_patient_assignments,
    get_patient_by_kakao_id,
    get_patient_sessions,
    get_video_jobs,
    link_kakao_user,
    save_kakao_session,
    update_video_job,
)
from dashboard.exercise_library import EXERCISE_NAMES
from dashboard.llm_client import generate_reply
from video_analyzer import analyze_video, delete_video_file, download_video

KAKAO_CHAT_SYSTEM_PROMPT = (
    "당신은 재활 운동 앱 'Care Flow'의 컴패니언 캐릭터 '새싹이'입니다. "
    "카카오톡으로 환자와 대화하고 있습니다. 짧고 다정하게 답하세요. "
    "의학적 진단이나 처방은 하지 말고, 통증을 호소하면 주치의에게 전달하겠다고 안내하세요."
)

REGISTRATION_PATTERN = re.compile(r"^\s*(\S+)\s+(\d{5})\s*$")

EXERCISE_START_PHRASES = ["운동 시작", "운동시작", "시작할게요", "운동 할게요", "운동할게요"]
EXERCISE_DONE_PHRASES = ["운동 완료", "운동완료", "운동 끝", "다 했어요", "끝났어요"]

SCALE_HINT = "(1~10 사이 숫자로 답해주세요. 1: 매우 낮음, 10: 매우 높음)"

# 각 항목: (field, question, is_scale). is_scale=True인 항목은 1~10 정수만 허용,
# 벗어나면 같은 질문을 다시 묻는다. memo는 자유 텍스트라 척도 검증 대상이 아니다.
PRE_SURVEY_QUESTIONS = [
    ("condition", f"오늘 컨디션은 어떠세요? {SCALE_HINT}", True),
    ("pain", f"지금 통증 수준은 몇 점인가요? {SCALE_HINT}", True),
    ("sleep", f"어젯밤 수면은 어떠셨나요? {SCALE_HINT}", True),
]
POST_SURVEY_QUESTIONS = [
    ("discomfort", f"운동 후 불편감은 어느 정도였나요? {SCALE_HINT}", True),
    ("fatigue", f"피로도는 어느 정도인가요? {SCALE_HINT}", True),
    ("memo", "오늘 하고 싶은 말이나 메모가 있으면 적어주세요. 없으면 '없음'이라고 답해주세요.", False),
]

# 영상 분석 결과를 기다리는 최대 시간. 카카오 콜백 토큰이 5분(300초)만 유효하므로
# 그보다 여유를 두고 240초로 제한한다. 이 시간이 지나도 안 끝난 작업은 재촬영 대상으로 처리한다.
WAIT_TIMEOUT_SECONDS = 240
WAIT_POLL_INTERVAL_SECONDS = 2


def _is_valid_scale_answer(text):
    text = text.strip()
    return text.isdigit() and 1 <= int(text) <= 10


def _simple_text_response(text):
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


def _callback_ack_response(text):
    return {
        "version": "2.0",
        "useCallback": True,
        "data": {"text": text},
    }


def _extract_utterance_and_user_id(payload):
    user_request = payload.get("userRequest", {})
    utterance = (user_request.get("utterance") or "").strip()
    kakao_user_id = user_request.get("user", {}).get("id", "")
    return utterance, kakao_user_id


def _extract_video_url(payload):
    trigger_type = payload.get("flow", {}).get("trigger", {}).get("type")
    if trigger_type != "IMAGE_UPLOAD":
        return None
    media = payload.get("userRequest", {}).get("params", {}).get("media", {})
    if media.get("type") != "video":
        return None
    return media.get("url") or None


def handle_skill_request(store_path, payload):
    """카카오 스킬 서버 요청 하나를 처리해서 응답 dict를 반환한다."""
    utterance, kakao_user_id = _extract_utterance_and_user_id(payload)
    if not kakao_user_id:
        return _simple_text_response("사용자 정보를 확인할 수 없어요. 잠시 후 다시 시도해주세요.")

    patient = get_patient_by_kakao_id(store_path, kakao_user_id)
    if patient is None:
        return _handle_identity_verification(store_path, kakao_user_id, utterance)

    callback_url = payload.get("userRequest", {}).get("callbackUrl")
    video_url = _extract_video_url(payload)
    session_state = get_kakao_session(store_path, kakao_user_id)
    state = session_state.get("state", "idle")

    if state == "exercising":
        return _handle_exercising_state(store_path, patient, kakao_user_id, session_state, utterance, video_url)

    if state == "reshooting":
        if video_url:
            return _handle_reshoot_video(store_path, patient, kakao_user_id, session_state, video_url, callback_url)
        return _handle_reshoot_text(store_path, kakao_user_id, session_state, utterance)

    if video_url:
        return _simple_text_response(
            "지금은 영상을 받을 수 있는 상태가 아니에요. \"운동 시작\"이라고 먼저 말씀해주세요."
        )

    if state in ("survey_pre", "survey_post"):
        phase = "pre" if state == "survey_pre" else "post"
        return _handle_survey_step(store_path, patient, kakao_user_id, session_state, utterance, phase, callback_url)

    if state == "awaiting_results":
        return _handle_awaiting_results(store_path, kakao_user_id)

    return _handle_idle_state(store_path, patient, kakao_user_id, utterance)


def _handle_identity_verification(store_path, kakao_user_id, utterance):
    match = REGISTRATION_PATTERN.match(utterance)
    if not match:
        return _simple_text_response(
            "안녕하세요! Care Flow입니다 🌱\n"
            "먼저 신원 확인이 필요해요. \"이름 등록번호\" 형식으로 보내주세요.\n"
            "예: 홍은결 52445"
        )

    name, registration_number = match.group(1), match.group(2)
    patient = find_patient_by_registration(store_path, name, registration_number)
    if patient is None:
        return _simple_text_response(
            "일치하는 환자 정보를 찾을 수 없어요. 이름과 등록번호를 다시 확인해서 보내주세요."
        )

    link_kakao_user(store_path, patient["id"], kakao_user_id)
    return _simple_text_response(
        f"{patient['name']}님, 확인됐어요! 👋 앞으로 이 창으로 편하게 대화하고 운동 안내도 받을 수 있어요.\n"
        "운동을 시작하시려면 \"운동 시작\"이라고 말해주세요."
    )


def _handle_idle_state(store_path, patient, kakao_user_id, utterance):
    if any(p in utterance for p in EXERCISE_START_PHRASES):
        save_kakao_session(store_path, kakao_user_id, {"state": "survey_pre", "step": 0, "answers": {}})
        _, question, _ = PRE_SURVEY_QUESTIONS[0]
        return _simple_text_response(f"운동 시작 전에 간단히 여쭤볼게요.\n\n{question}")

    if any(p in utterance for p in EXERCISE_DONE_PHRASES):
        save_kakao_session(store_path, kakao_user_id, {"state": "survey_post", "step": 0, "answers": {}})
        _, question, _ = POST_SURVEY_QUESTIONS[0]
        return _simple_text_response(f"오늘 운동 마무리하기 전에 몇 가지 여쭤볼게요.\n\n{question}")

    return _handle_general_chat(store_path, patient, utterance)


def _handle_general_chat(store_path, patient, utterance):
    if not utterance:
        return _simple_text_response("메시지를 다시 보내주세요.")

    patient_id = patient["id"]
    context = _build_kakao_chat_context(store_path, patient_id)
    try:
        reply = generate_reply(f"{KAKAO_CHAT_SYSTEM_PROMPT}\n\n{context}", utterance)
    except Exception:
        return _simple_text_response("죄송해요, 지금은 답변하기 어려워요. 잠시 후 다시 시도해주세요.")

    now = datetime.now().isoformat()
    append_chat_log(store_path, {
        "patient_id": patient_id, "channel": "kakao", "role": "user",
        "message": utterance, "timestamp": now,
    })
    append_chat_log(store_path, {
        "patient_id": patient_id, "channel": "kakao", "role": "bot",
        "message": reply, "timestamp": now,
    })
    return _simple_text_response(reply)


def _build_kakao_chat_context(store_path, patient_id):
    sessions = get_patient_sessions(store_path, patient_id)
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent = [s for s in sessions if s.get("ended_at", "") >= cutoff]
    if not recent:
        return "최근 30일 운동 기록: 없음"
    lines = [
        f"- {s.get('ended_at', '')[:10]} "
        f"{EXERCISE_NAMES.get(s.get('exercise_key', ''), s.get('exercise_key', ''))} "
        f"{'목표 달성' if s.get('target_reached') else '목표 미달성'}"
        for s in recent
    ]
    return "최근 30일 운동 기록:\n" + "\n".join(lines)


# --- 문진 (운동 전 / 운동 후) ---

def _handle_survey_step(store_path, patient, kakao_user_id, session_state, utterance, phase, callback_url=None):
    questions = PRE_SURVEY_QUESTIONS if phase == "pre" else POST_SURVEY_QUESTIONS
    step = session_state.get("step", 0)
    answers = dict(session_state.get("answers", {}))

    if not utterance:
        _, question, _ = questions[step]
        return _simple_text_response(question)

    field, question, is_scale = questions[step]
    if is_scale and not _is_valid_scale_answer(utterance):
        return _simple_text_response(f"1~10 사이 숫자로 다시 답해주세요.\n\n{question}")

    answers[field] = utterance
    step += 1

    if step < len(questions):
        save_kakao_session(store_path, kakao_user_id, {"state": f"survey_{phase}", "step": step, "answers": answers})
        _, next_question, _ = questions[step]
        return _simple_text_response(next_question)

    append_chat_log(store_path, {
        "patient_id": patient["id"], "channel": "kakao", "role": "user",
        "type": "survey", "phase": phase, "answers": answers,
        "timestamp": datetime.now().isoformat(),
    })

    if phase == "pre":
        return _start_exercise_flow(store_path, patient, kakao_user_id)

    return _finalize_or_wait_for_results(store_path, kakao_user_id, callback_url)


# --- 운동 진행 (배정 운동을 순서대로 확인) ---

def _start_exercise_flow(store_path, patient, kakao_user_id):
    """문진(운동 전)이 끝난 뒤 배정 운동 목록을 보여주고, 순서대로 확인받을 준비를 한다."""
    assignments = get_patient_assignments(store_path, patient["id"])
    if not assignments:
        save_kakao_session(store_path, kakao_user_id, {"state": "idle"})
        return _simple_text_response("설문 감사해요! 아직 배정된 운동이 없어요. 주치의 선생님께 문의해주세요.")

    save_kakao_session(store_path, kakao_user_id, {
        "state": "exercising", "assignments": assignments, "current_index": 0,
    })

    lines = [
        f"{i + 1}. {EXERCISE_NAMES.get(a['exercise_key'], a['exercise_key'])} — 목표 {a['target_reps']}회"
        for i, a in enumerate(assignments)
    ]
    first_name = EXERCISE_NAMES.get(assignments[0]["exercise_key"], assignments[0]["exercise_key"])
    return _simple_text_response(
        "설문 감사해요! 오늘 배정된 운동입니다:\n\n"
        + "\n".join(lines)
        + f"\n\n먼저 '{first_name}' 운동을 하시고, 영상으로 보내주시거나 어려우면 '했어요'라고 말해주세요!"
    )


def _handle_exercising_state(store_path, patient, kakao_user_id, session_state, utterance, video_url):
    assignments = session_state.get("assignments", [])
    index = session_state.get("current_index", 0)
    current = assignments[index]
    exercise_key = current["exercise_key"]

    if video_url:
        job_id = create_video_job(store_path, kakao_user_id, exercise_key, current.get("target_reps"))
        _start_background(_analyze_and_store_job, store_path, kakao_user_id, job_id, exercise_key, video_url)
        exercise_name = EXERCISE_NAMES.get(exercise_key, exercise_key)
        return _advance_exercise(store_path, kakao_user_id, session_state, f"'{exercise_name}' 영상 잘 받았어요! (분석은 잠시 후 완료돼요)")

    if utterance:
        now = datetime.now(timezone.utc).isoformat()
        append_session(store_path, {
            "session_id": uuid.uuid4().hex[:8], "patient_id": patient["id"], "exercise_key": exercise_key,
            "started_at": now, "ended_at": now, "video_path": None,
            "final_count": None, "target_reached": None, "source": "kakao_manual",
        })
        exercise_name = EXERCISE_NAMES.get(exercise_key, exercise_key)
        return _advance_exercise(store_path, kakao_user_id, session_state, f"'{exercise_name}' 완료로 기록했어요!")

    return _simple_text_response("운동을 완료하시면 영상을 보내주시거나 '했어요'라고 말해주세요!")


def _advance_exercise(store_path, kakao_user_id, session_state, prefix_text):
    assignments = session_state.get("assignments", [])
    index = session_state.get("current_index", 0)
    next_index = index + 1

    if next_index < len(assignments):
        save_kakao_session(store_path, kakao_user_id, {**session_state, "current_index": next_index})
        next_name = EXERCISE_NAMES.get(assignments[next_index]["exercise_key"], assignments[next_index]["exercise_key"])
        return _simple_text_response(
            f"{prefix_text}\n\n다음은 '{next_name}' 운동입니다. 영상으로 보내주시거나 어려우면 '했어요'라고 말해주세요!"
        )

    save_kakao_session(store_path, kakao_user_id, {"state": "survey_post", "step": 0, "answers": {}})
    _, first_question, _ = POST_SURVEY_QUESTIONS[0]
    return _simple_text_response(
        f"{prefix_text}\n\n오늘 배정된 운동을 모두 확인했어요! 마무리로 몇 가지 여쭤볼게요.\n\n{first_question}"
    )


def _analyze_and_store_job(store_path, kakao_user_id, job_id, exercise_key, video_url):
    local_path = os.path.join(tempfile.gettempdir(), f"kakao_video_{uuid.uuid4().hex}.mp4")
    try:
        download_video(video_url, local_path)
        result = analyze_video(local_path, exercise_key)
        update_video_job(
            store_path, kakao_user_id, job_id,
            status="done", pose_detected=result["pose_detected"], final_value=result["final_value"],
        )
    except Exception:
        update_video_job(store_path, kakao_user_id, job_id, status="done", pose_detected=False, final_value=None)
    finally:
        delete_video_file(local_path)


# --- 운동 후 문진 완료 시점: 분석 결과 종합 (즉시 또는 콜백으로 대기) ---

def _finalize_or_wait_for_results(store_path, kakao_user_id, callback_url):
    jobs = get_video_jobs(store_path, kakao_user_id)
    pending = [j for j in jobs if j["status"] == "pending"]

    if not pending:
        text, next_state = _build_final_summary(store_path, kakao_user_id, jobs)
        save_kakao_session(store_path, kakao_user_id, next_state)
        return _simple_text_response(text)

    save_kakao_session(store_path, kakao_user_id, {"state": "awaiting_results"})

    if not callback_url:
        return _simple_text_response(
            "모든 답변 감사해요! 영상 분석이 아직 진행 중이에요. 잠시 후 아무 메시지나 보내주시면 결과를 알려드릴게요."
        )

    _start_background(_wait_for_jobs_then_callback, store_path, kakao_user_id, callback_url)
    return _callback_ack_response("모든 답변 감사해요! 영상 분석이 끝나면 결과를 알려드릴게요. 잠시만 기다려주세요 🌱")


def _handle_awaiting_results(store_path, kakao_user_id):
    jobs = get_video_jobs(store_path, kakao_user_id)
    if any(j["status"] == "pending" for j in jobs):
        return _simple_text_response("아직 영상 분석이 진행 중이에요. 조금만 더 기다려주세요 🙏")

    text, next_state = _build_final_summary(store_path, kakao_user_id, jobs)
    save_kakao_session(store_path, kakao_user_id, next_state)
    return _simple_text_response(text)


def _wait_for_jobs_then_callback(store_path, kakao_user_id, callback_url):
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        jobs = get_video_jobs(store_path, kakao_user_id)
        if not any(j["status"] == "pending" for j in jobs):
            break
        time.sleep(WAIT_POLL_INTERVAL_SECONDS)

    jobs = get_video_jobs(store_path, kakao_user_id)
    text, next_state = _build_final_summary(store_path, kakao_user_id, jobs)
    save_kakao_session(store_path, kakao_user_id, next_state)
    _send_callback(callback_url, text)


def _build_final_summary(store_path, kakao_user_id, jobs):
    """영상 작업 결과를 세션으로 기록하고, 응답 문구와 다음 상태를 만든다.

    완료(포즈 인식 성공) 건은 여기서 session으로 기록한다 — 아직 어디에도 기록 안 된
    상태이기 때문(작업 등록 시점엔 세션을 만들지 않고 job만 만들어둔다).
    타임아웃까지 못 끝난 작업(status=pending)도 재촬영 대상으로 취급한다.
    """
    patient = get_patient_by_kakao_id(store_path, kakao_user_id)
    patient_id = patient["id"] if patient else None

    completed = [j for j in jobs if j["status"] == "done" and j["pose_detected"]]
    unresolved = [j for j in jobs if not (j["status"] == "done" and j["pose_detected"])]

    lines = []
    for job in completed:
        final_value = job["final_value"]
        target_reps = job.get("target_reps")
        target_reached = target_reps is not None and final_value >= target_reps
        exercise_name = EXERCISE_NAMES.get(job["exercise_key"], job["exercise_key"])
        now = datetime.now(timezone.utc).isoformat()
        append_session(store_path, {
            "session_id": uuid.uuid4().hex[:8], "patient_id": patient_id, "exercise_key": job["exercise_key"],
            "started_at": now, "ended_at": now, "video_path": None,
            "final_count": final_value, "target_reached": target_reached, "source": "kakao_video",
        })
        lines.append(f"- {exercise_name}: {final_value}회 ({'달성' if target_reached else '미달성'})")

    clear_video_jobs(store_path, kakao_user_id)

    summary_prefix = ("영상 분석 결과예요:\n" + "\n".join(lines) + "\n\n") if lines else ""

    if unresolved:
        reshoot_keys = [j["exercise_key"] for j in unresolved]
        reshoot_names = ", ".join(EXERCISE_NAMES.get(k, k) for k in reshoot_keys)
        first_name = EXERCISE_NAMES.get(reshoot_keys[0], reshoot_keys[0])
        text = (
            summary_prefix
            + f"다음 운동은 영상에서 자세가 잘 인식되지 않았어요: {reshoot_names}\n\n"
            + f"먼저 '{first_name}' 운동을 다시 촬영해서 보내주세요. 어려우면 '어려워요'라고 답해주세요."
        )
        next_state = {"state": "reshooting", "queue": reshoot_keys, "index": 0}
    else:
        text = summary_prefix + "오늘 운동 정말 잘 하셨어요! 기록 남겨드렸습니다 🌱 다음에 또 만나요!"
        next_state = {"state": "idle"}

    return text, next_state


# --- 재촬영 ---

def _handle_reshoot_video(store_path, patient, kakao_user_id, session_state, video_url, callback_url):
    queue = session_state.get("queue", [])
    index = session_state.get("index", 0)
    exercise_key = queue[index]
    assignments = get_patient_assignments(store_path, patient["id"])
    target_reps = next((a["target_reps"] for a in assignments if a["exercise_key"] == exercise_key), None)

    if not callback_url:
        return _simple_text_response("죄송해요, 지금은 영상을 처리할 수 없어요. 잠시 후 다시 시도해주세요.")

    _start_background(
        _analyze_reshoot_and_callback,
        store_path, patient["id"], kakao_user_id, exercise_key, target_reps, video_url, callback_url,
    )
    return _callback_ack_response("영상을 확인하고 있어요! 잠시만 기다려주세요 🌱")


def _analyze_reshoot_and_callback(store_path, patient_id, kakao_user_id, exercise_key, target_reps, video_url, callback_url):
    local_path = os.path.join(tempfile.gettempdir(), f"kakao_video_{uuid.uuid4().hex}.mp4")
    exercise_name = EXERCISE_NAMES.get(exercise_key, exercise_key)
    try:
        download_video(video_url, local_path)
        result = analyze_video(local_path, exercise_key)
    except Exception:
        _send_callback(callback_url, "영상을 처리하는 중 문제가 생겼어요. 다시 한 번 시도해주시겠어요?")
        return
    finally:
        delete_video_file(local_path)

    now = datetime.now(timezone.utc).isoformat()
    if result["pose_detected"]:
        final_value = result["final_value"]
        target_reached = target_reps is not None and final_value >= target_reps
        append_session(store_path, {
            "session_id": uuid.uuid4().hex[:8], "patient_id": patient_id, "exercise_key": exercise_key,
            "started_at": now, "ended_at": now, "video_path": None,
            "final_count": final_value, "target_reached": target_reached, "source": "kakao_video",
        })
        status_text = "목표를 달성했어요! 🎉" if target_reached else "수고하셨어요! (목표에는 조금 못 미쳤어요)"
        prefix = f"'{exercise_name}' {final_value}회 확인했어요. {status_text}"
    else:
        append_session(store_path, {
            "session_id": uuid.uuid4().hex[:8], "patient_id": patient_id, "exercise_key": exercise_key,
            "started_at": now, "ended_at": now, "video_path": None,
            "final_count": None, "target_reached": False, "source": "kakao_video",
        })
        prefix = f"'{exercise_name}' 영상에서도 자세가 잘 인식되지 않았어요. 완료로 기록하고 넘어갈게요."

    _advance_reshoot_and_send_callback(store_path, kakao_user_id, callback_url, prefix)


def _advance_reshoot_and_send_callback(store_path, kakao_user_id, callback_url, prefix):
    session_state = get_kakao_session(store_path, kakao_user_id)
    queue = session_state.get("queue", [])
    index = session_state.get("index", 0) + 1

    if index < len(queue):
        save_kakao_session(store_path, kakao_user_id, {"state": "reshooting", "queue": queue, "index": index})
        next_name = EXERCISE_NAMES.get(queue[index], queue[index])
        _send_callback(
            callback_url,
            f"{prefix}\n\n다음은 '{next_name}' 다시 촬영해서 보내주세요. 어려우면 '어려워요'라고 답해주세요.",
        )
    else:
        save_kakao_session(store_path, kakao_user_id, {"state": "idle"})
        _send_callback(callback_url, f"{prefix}\n\n오늘 운동 기록을 모두 정리했어요! 다음에 또 만나요 🌱")


def _handle_reshoot_text(store_path, kakao_user_id, session_state, utterance):
    queue = session_state.get("queue", [])
    index = session_state.get("index", 0)
    exercise_key = queue[index]
    exercise_name = EXERCISE_NAMES.get(exercise_key, exercise_key)

    if not utterance:
        return _simple_text_response(f"'{exercise_name}' 운동을 다시 촬영해서 보내주시거나, 어려우면 '어려워요'라고 답해주세요.")

    next_index = index + 1
    if next_index < len(queue):
        save_kakao_session(store_path, kakao_user_id, {"state": "reshooting", "queue": queue, "index": next_index})
        next_name = EXERCISE_NAMES.get(queue[next_index], queue[next_index])
        return _simple_text_response(
            f"알겠어요! '{exercise_name}'는 넘어갈게요.\n\n"
            f"다음은 '{next_name}' 다시 촬영해서 보내주세요. 어려우면 '어려워요'라고 답해주세요."
        )

    save_kakao_session(store_path, kakao_user_id, {"state": "idle"})
    return _simple_text_response(
        f"알겠어요! '{exercise_name}'는 넘어갈게요.\n\n오늘 운동 기록을 모두 정리했어요! 다음에 또 만나요 🌱"
    )


# --- 공용 유틸 ---

def _start_background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _send_callback(callback_url, text):
    body = json.dumps({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }).encode("utf-8")
    req = urllib.request.Request(
        callback_url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # best-effort — 콜백 전송이 실패해도 서버가 할 수 있는 추가 조치는 없다
