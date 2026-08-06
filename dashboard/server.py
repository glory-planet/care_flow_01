import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, redirect, send_file, send_from_directory, session

from dashboard.data_store import (
    DEFAULT_STORE_PATH,
    add_patient,
    append_chat_log,
    assign_patient_to_doctor,
    authenticate_user,
    get_patient,
    get_patient_assignments,
    get_patient_sessions,
    get_patients,
    load_store,
    save_assignments,
    save_patient_assignments,
)
from dashboard.exercise_library import EXERCISE_NAMES
from dashboard.hospital_rag import lookup_patient_by_unique_id
from dashboard.kakao_skill import handle_skill_request
from dashboard.llm_client import generate_reply
from dashboard.s3_client import generate_upload_url, generate_download_url
from dashboard.cognito_client import authenticate as cognito_authenticate
from dashboard.knowledge_base import build_rag_context

PATIENT_NAME = "홍은결"
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(DASHBOARD_DIR)
MAIN_PY_PATH = os.path.join(PROJECT_ROOT, "main.py")
STRETCH_REMINDER_PATH = os.path.join(PROJECT_ROOT, "stretch_reminder.py")
RECORDINGS_DIR = os.path.join(DASHBOARD_DIR, "recordings")

STORE_PATH = DEFAULT_STORE_PATH
stretch_reminder_process = None

app = Flask(__name__)
app.secret_key = "sesak-care-dev-secret-key-2026"


def build_recording_filename(exercise_key, session_id, timestamp=None):
    """환자명_시간_운동명_세션ID.webm 형식의 녹화 파일명을 만든다."""
    timestamp = timestamp or datetime.now()
    time_part = timestamp.strftime("%Y%m%d_%H%M%S")
    exercise_name = EXERCISE_NAMES.get(exercise_key, exercise_key)
    return f"{PATIENT_NAME}_{time_part}_{exercise_name}_{session_id}.webm"


@app.route("/")
def index():
    if "user" in session:
        return redirect("/dashboard")
    return send_from_directory(DASHBOARD_DIR, "login.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    user = session["user"]
    if user["role"] == "doctor":
        return send_from_directory(DASHBOARD_DIR, "doctor.html")
    return send_from_directory(DASHBOARD_DIR, "patient.html")


@app.route("/doctor/patient/<patient_id>")
def doctor_patient_detail(patient_id):
    if "user" not in session or session["user"]["role"] != "doctor":
        return redirect("/")
    return send_from_directory(DASHBOARD_DIR, "patient-detail.html")


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")

    # Cognito 인증
    result = cognito_authenticate(username, password)
    if not result["authenticated"]:
        return jsonify({"ok": False, "error": result.get("error", "invalid credentials")})

    groups = result["groups"]
    role = "doctor" if "doctor" in groups else "patient"
    user_attrs = result["attributes"]
    display_name = user_attrs.get("name", username)

    # DynamoDB에서 추가 정보 조회 (patient_id, patient_ids)
    user_data = authenticate_user(STORE_PATH, username, password)
    patient_id = None
    patient_ids = None
    if user_data:
        patient_id = user_data.get("patient_id")
        patient_ids = user_data.get("patient_ids")

    session["user"] = {
        "username": username,
        "role": role,
        "name": display_name,
        "patient_id": patient_id,
        "patient_ids": patient_ids,
        "access_token": result["tokens"]["access_token"],
    }
    return jsonify({"ok": True, "role": role, "name": display_name})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"ok": True})


@app.route("/api/me", methods=["GET"])
def me():
    user = session.get("user")
    if user is None:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, **user})


@app.route("/assets/<path:filepath>")
def serve_assets(filepath):
    return send_from_directory(os.path.join(DASHBOARD_DIR, "assets"), filepath)


@app.route("/api/start-exercise", methods=["POST"])
def start_exercise():
    data = request.get_json()
    exercise_key = data["exercise_key"]
    patient_id = data.get("patient_id")
    store = load_store(STORE_PATH)
    assignment = next((a for a in store["assignments"] if a["exercise_key"] == exercise_key), None)
    target_reps = assignment["target_reps"] if assignment else None

    session_id = uuid.uuid4().hex[:8]
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    output_path = os.path.join(RECORDINGS_DIR, build_recording_filename(exercise_key, session_id))

    cmd = [
        sys.executable, MAIN_PY_PATH,
        "--exercise", exercise_key,
        "--output", output_path,
        "--session-id", session_id,
        "--store", STORE_PATH,
    ]
    if target_reps is not None:
        cmd += ["--target-reps", str(target_reps)]
    if patient_id:
        cmd += ["--patient-id", patient_id]

    subprocess.Popen(cmd, cwd=PROJECT_ROOT)
    return jsonify({"session_id": session_id})


@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    store = load_store(STORE_PATH)
    sessions = sorted(store["sessions"], key=lambda s: s.get("ended_at", ""), reverse=True)
    return jsonify(sessions)


@app.route("/api/video/<session_id>", methods=["GET"])
def get_video(session_id):
    store = load_store(STORE_PATH)
    sess = next((s for s in store["sessions"] if s["session_id"] == session_id), None)
    if sess is None:
        return jsonify({"error": "video not found"}), 404
    s3_key = sess.get("video_s3_key")
    if s3_key:
        # S3에 저장된 영상 — Presigned URL로 리다이렉트
        url = generate_download_url(s3_key)
        return redirect(url)
    # 레거시: 로컬 파일 경로
    video_path = sess.get("video_path")
    if not video_path or not os.path.exists(video_path):
        return jsonify({"error": "video not found"}), 404
    return send_file(video_path)


@app.route("/api/upload-url", methods=["POST"])
def get_upload_url():
    """영상 업로드용 S3 Presigned URL을 발급한다."""
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    session_id = data.get("session_id")
    exercise_key = data.get("exercise_key")
    if not all([patient_id, session_id, exercise_key]):
        return jsonify({"error": "patient_id, session_id, exercise_key required"}), 400
    result = generate_upload_url(patient_id, session_id, exercise_key)
    return jsonify(result)


@app.route("/api/patients", methods=["GET"])
def list_patients():
    patients = get_patients(STORE_PATH)
    return jsonify(patients)


@app.route("/api/hospital-lookup/<unique_id>", methods=["GET"])
def hospital_lookup(unique_id):
    """병원 정보(가짜 EMR/S3 Vectors RAG)에서 고유 ID로 환자 정보를 조회한다.

    환자 등록 화면에서 주치의가 고유 ID를 입력하면 이름/나이/진단명을 자동완성하는 데 쓴다.
    """
    user = session.get("user")
    if not user or user["role"] != "doctor":
        return jsonify({"error": "forbidden"}), 403

    try:
        result = lookup_patient_by_unique_id(unique_id)
    except Exception:
        app.logger.exception("hospital lookup failed")
        return jsonify({"error": "lookup_unavailable"}), 503

    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)


@app.route("/api/patients", methods=["POST"])
def register_patient():
    """신규 환자를 등록한다. id와 registration_number는 동일한 5자리 고유번호로 발급된다."""
    user = session.get("user")
    if not user or user["role"] != "doctor":
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    age = data.get("age")
    diagnosis = (data.get("diagnosis") or "").strip()
    joint = data.get("joint")

    patient = add_patient(STORE_PATH, name, age, diagnosis, joint)
    assign_patient_to_doctor(STORE_PATH, user["username"], patient["id"])

    # 세션에 캐시된 patient_ids도 갱신해서 이번 요청부터 바로 목록에 보이게 한다.
    # dict를 in-place로 mutate하면 Flask 세션이 변경을 감지하지 못할 수 있으므로
    # session["user"] 전체를 새 dict로 재할당한다.
    patient_ids = list(user.get("patient_ids") or [])
    if patient["id"] not in patient_ids:
        patient_ids.append(patient["id"])
    session["user"] = {**user, "patient_ids": patient_ids}

    return jsonify(patient), 201


@app.route("/api/patients/<patient_id>", methods=["GET"])
def get_patient_detail(patient_id):
    patient = get_patient(STORE_PATH, patient_id)
    if patient is None:
        return jsonify({"error": "patient not found"}), 404
    return jsonify(patient)


@app.route("/api/patients/<patient_id>/assignments", methods=["GET"])
def get_patient_assignments_api(patient_id):
    today = date.today().isoformat()
    assignments = get_patient_assignments(STORE_PATH, patient_id)
    sessions = get_patient_sessions(STORE_PATH, patient_id)
    completed_keys = {
        s["exercise_key"]
        for s in sessions
        if s.get("ended_at", "").startswith(today) and s.get("target_reached")
    }
    result = [
        {**a, "completed": a["exercise_key"] in completed_keys}
        for a in assignments
    ]
    return jsonify(result)


@app.route("/api/patients/<patient_id>/assignments", methods=["POST"])
def post_patient_assignments_api(patient_id):
    assignments = request.get_json()["assignments"]
    save_patient_assignments(STORE_PATH, patient_id, assignments)
    return jsonify({"ok": True})


@app.route("/api/patients/<patient_id>/sessions", methods=["GET"])
def get_patient_sessions_api(patient_id):
    sessions = get_patient_sessions(STORE_PATH, patient_id)
    assignments = get_patient_assignments(STORE_PATH, patient_id)
    # 배정 목표 횟수 맵
    target_map = {a["exercise_key"]: a["target_reps"] for a in assignments}
    # 날짜 필터 지원: ?date=2026-08-03
    filter_date = request.args.get("date")
    if filter_date:
        sessions = [s for s in sessions if s.get("ended_at", "").startswith(filter_date)]
    sessions = sorted(sessions, key=lambda s: s.get("ended_at", ""), reverse=True)
    # 각 세션에 target_reps 첨부
    result = [
        {**s, "target_reps": target_map.get(s["exercise_key"])}
        for s in sessions
    ]
    return jsonify(result)


PATIENT_CHAT_SYSTEM_PROMPT = (
    "당신은 재활 운동 앱 'Care Flow'의 컴패니언 캐릭터 '새싹이'입니다. "
    "환자를 따뜻하고 다정하게 격려하는 말투로 짧게 대답하세요. "
    "의학적 진단이나 처방은 하지 말고, 통증을 호소하면 주치의에게 전달하겠다고 안내하세요."
)


def _require_message(data):
    return data.get("message", "").strip()


def _build_patient_chat_context(patient_id):
    sessions = get_patient_sessions(STORE_PATH, patient_id)
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


@app.route("/api/chat", methods=["POST"])
def patient_chat():
    user = session.get("user")
    if not user or user["role"] != "patient":
        return jsonify({"error": "forbidden"}), 403

    if not user.get("patient_id"):
        return jsonify({"error": "forbidden"}), 403

    message = _require_message(request.get_json(silent=True) or {})
    if not message:
        return jsonify({"error": "message is required"}), 400

    patient_id = user["patient_id"]

    context = _build_patient_chat_context(patient_id)
    rag_context = build_rag_context(message)
    full_context = context + ("\n\n" + rag_context if rag_context else "")
    try:
        reply = generate_reply(f"{PATIENT_CHAT_SYSTEM_PROMPT}\n\n{full_context}", message)
    except Exception:
        app.logger.exception("LLM call failed")
        return jsonify({"error": "llm_unavailable"}), 503

    append_chat_log(STORE_PATH, {
        "patient_id": patient_id, "channel": "web", "role": "user",
        "message": message, "timestamp": datetime.now().isoformat(),
    })
    append_chat_log(STORE_PATH, {
        "patient_id": patient_id, "channel": "web", "role": "bot",
        "message": reply, "timestamp": datetime.now().isoformat(),
    })

    return jsonify({"reply": reply})


DOCTOR_CHAT_SYSTEM_PROMPT = (
    "당신은 재활 운동 앱 'Care Flow'의 주치의용 AI 어시스턴트입니다. "
    "아래 제공된 환자 데이터만 근거로 간결하고 사실 기반으로 답변하세요. "
    "데이터에 없는 내용은 추측하지 말고 모른다고 답하세요."
)


def _summarize_patient_for_doctor_chat(store, patient_id, week_start, today):
    patient = next((p for p in store["patients"] if p["id"] == patient_id), None)
    if patient is None:
        return None
    sessions_all = [s for s in store["sessions"] if s.get("patient_id") == patient_id]
    recent = [s for s in sessions_all if s.get("ended_at", "")[:10] >= week_start.isoformat()]
    reached = sum(1 for s in recent if s.get("target_reached"))
    return (
        f"- {patient['name']} (id={patient_id}, {patient.get('diagnosis', '')}): "
        f"최근 7일 세션 {len(recent)}건, 목표 달성 {reached}건"
    )


def _build_doctor_chat_context(patient_ids, target_patient_id):
    store = load_store(STORE_PATH)
    today = date.today()
    week_start = today - timedelta(days=6)

    if target_patient_id:
        line = _summarize_patient_for_doctor_chat(store, target_patient_id, week_start, today)
        if line is None:
            return None
        return f"환자 정보:\n{line}"

    lines = [
        _summarize_patient_for_doctor_chat(store, pid, week_start, today)
        for pid in patient_ids
    ]
    lines = [l for l in lines if l is not None]
    return "담당 환자 전체 요약:\n" + ("\n".join(lines) if lines else "담당 환자 없음")


@app.route("/api/doctor/chat", methods=["POST"])
def doctor_chat():
    user = session.get("user")
    if not user or user["role"] != "doctor":
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    message = _require_message(data)
    target_patient_id = data.get("patient_id")
    if not message:
        return jsonify({"error": "message is required"}), 400

    patient_ids = user.get("patient_ids") or []

    if target_patient_id and target_patient_id not in patient_ids:
        return jsonify({"error": "forbidden"}), 403

    context = _build_doctor_chat_context(patient_ids, target_patient_id)
    if context is None:
        return jsonify({"error": "patient not found"}), 404

    try:
        reply = generate_reply(f"{DOCTOR_CHAT_SYSTEM_PROMPT}\n\n{context}", message)
    except Exception:
        app.logger.exception("LLM call failed")
        return jsonify({"error": "llm_unavailable"}), 503

    return jsonify({"reply": reply})


def build_stats_summary(active_days, total_days, achieve_rate):
    """주간 통계 요약 문장을 생성한다."""
    attend_rate = round(active_days / total_days * 100) if total_days > 0 else 0
    tail = (
        "목표 달성이 우수합니다." if achieve_rate >= 80 else
        "꾸준히 참여하고 있으나 목표 미달성이 확인됩니다." if achieve_rate >= 50 else
        "출석 독려가 필요합니다."
    )
    return (
        f"최근 7일 출석률 {attend_rate}%({active_days}/{total_days}일). "
        f"최근 7일 배정 운동 달성률은 {achieve_rate}%입니다. {tail}"
    )


@app.route("/api/patients/<patient_id>/stats", methods=["GET"])
def get_patient_stats(patient_id):
    """주간/월간 달성률을 반환한다."""
    sessions = get_patient_sessions(STORE_PATH, patient_id)
    assignments = get_patient_assignments(STORE_PATH, patient_id)
    today = date.today()

    # 주간: 이번 주 월요일부터 오늘까지
    week_start = today - timedelta(days=today.weekday())
    # 월간: 이번 달 1일부터 오늘까지
    month_start = today.replace(day=1)

    def count_for_range(start_date, end_date):
        """기간 내 각 날짜별 배정 운동 중 달성한 수를 계산."""
        total = 0
        achieved = 0
        d = start_date
        while d <= end_date:
            day_str = d.isoformat()
            day_sessions = [s for s in sessions if s.get("ended_at", "").startswith(day_str)]
            reached_keys = {s["exercise_key"] for s in day_sessions if s.get("target_reached")}
            total += len(assignments)
            achieved += len(reached_keys & {a["exercise_key"] for a in assignments})
            d += timedelta(days=1)
        return total, achieved

    week_total, week_achieved = count_for_range(week_start, today)
    month_total, month_achieved = count_for_range(month_start, today)

    rolling_start = today - timedelta(days=6)
    active_days = len({
        s.get("ended_at", "")[:10] for s in sessions
        if rolling_start.isoformat() <= s.get("ended_at", "")[:10] <= today.isoformat()
    })
    rolling_total, rolling_achieved = count_for_range(rolling_start, today)
    rolling_rate = round(rolling_achieved / rolling_total * 100) if rolling_total > 0 else 0

    # 캘린더용: 세션이 있는 날짜 목록과 해당 날짜의 달성 여부
    session_dates = {}
    for s in sessions:
        d = s.get("ended_at", "")[:10]
        if d not in session_dates:
            session_dates[d] = {"total": 0, "reached": 0}
        session_dates[d]["total"] += 1
        if s.get("target_reached"):
            session_dates[d]["reached"] += 1

    week_rate = round(week_achieved / week_total * 100) if week_total > 0 else 0

    return jsonify({
        "weekly": {
            "total": week_total,
            "achieved": week_achieved,
            "rate": week_rate,
        },
        "monthly": {
            "total": month_total,
            "achieved": month_achieved,
            "rate": round(month_achieved / month_total * 100) if month_total > 0 else 0,
        },
        "session_dates": session_dates,
        "attendance": {
            "active_days": active_days,
            "total_days": 7,
            "rate": round(active_days / 7 * 100),
            "achieve_rate": rolling_rate,
        },
        "summary": build_stats_summary(active_days, 7, rolling_rate),
    })


@app.route("/api/stretch-reminder/status", methods=["GET"])
def stretch_reminder_status():
    running = stretch_reminder_process is not None and stretch_reminder_process.poll() is None
    return jsonify({"running": running})


@app.route("/api/stretch-reminder/start", methods=["POST"])
def stretch_reminder_start():
    global stretch_reminder_process
    if stretch_reminder_process is None or stretch_reminder_process.poll() is not None:
        stretch_reminder_process = subprocess.Popen([sys.executable, STRETCH_REMINDER_PATH], cwd=PROJECT_ROOT)
    return jsonify({"running": True})


@app.route("/api/stretch-reminder/stop", methods=["POST"])
def stretch_reminder_stop():
    global stretch_reminder_process
    if stretch_reminder_process is not None and stretch_reminder_process.poll() is None:
        stretch_reminder_process.terminate()
    stretch_reminder_process = None
    return jsonify({"running": False})


@app.route("/kakao/skill", methods=["POST"])
def kakao_skill():
    payload = request.get_json(silent=True) or {}
    if os.environ.get("KAKAO_DEBUG_LOG"):
        try:
            debug_path = os.path.join(PROJECT_ROOT, "kakao_debug_log.jsonl")
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            app.logger.exception("failed to write kakao debug log")
    response = handle_skill_request(STORE_PATH, payload)
    return jsonify(response)


@app.route("/api/doctor/patients-summary", methods=["GET"])
def doctor_patients_summary():
    """주치의 담당 환자 목록 + 출석률/마지막 활동 요약."""
    user = session.get("user")
    if not user or user["role"] != "doctor":
        return jsonify({"error": "forbidden"}), 403

    patient_ids = user.get("patient_ids", [])
    store = load_store(STORE_PATH)
    today = date.today()
    week_start = today - timedelta(days=6)  # 최근 7일

    results = []
    for pid in patient_ids:
        patient = next((p for p in store["patients"] if p["id"] == pid), None)
        if patient is None:
            continue

        # 해당 환자의 배정 운동과 세션
        assignments = [a for a in store["assignments"] if a.get("patient_id") == pid]
        sessions_all = [s for s in store["sessions"] if s.get("patient_id") == pid]

        # 최근 7일 출석률 계산
        total = 0
        achieved = 0
        d = week_start
        while d <= today:
            day_str = d.isoformat()
            day_sessions = [s for s in sessions_all if s.get("ended_at", "").startswith(day_str)]
            reached_keys = {s["exercise_key"] for s in day_sessions if s.get("target_reached")}
            total += len(assignments)
            achieved += len(reached_keys & {a["exercise_key"] for a in assignments})
            d += timedelta(days=1)

        weekly_rate = round(achieved / total * 100) if total > 0 else 0

        # 마지막 활동 시간
        patient_sessions_sorted = sorted(
            sessions_all, key=lambda s: s.get("ended_at", ""), reverse=True
        )
        last_activity = patient_sessions_sorted[0].get("ended_at") if patient_sessions_sorted else None

        results.append({
            "id": pid,
            "name": patient["name"],
            "age": patient.get("age"),
            "diagnosis": patient.get("diagnosis", ""),
            "registered_at": patient.get("registered_at", ""),
            "weekly_rate": weekly_rate,
            "last_activity": last_activity,
        })

    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
