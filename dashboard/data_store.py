import json
import os
import random
import uuid
from datetime import datetime

DEFAULT_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "store.json")


def authenticate_user(path, username, password):
    """username/password로 사용자를 인증한다. 성공 시 user dict, 실패 시 None."""
    store = load_store(path)
    users = store.get("users", [])
    for user in users:
        if user["username"] == username and user["password"] == password:
            return user
    return None


def _default_store():
    return {
        "users": [], "patients": [], "assignments": [], "sessions": [], "chat_logs": [],
        "kakao_sessions": {}, "video_jobs": {},
    }


def load_store(path):
    if not os.path.exists(path):
        return _default_store()

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return _default_store()

    data.setdefault("users", [])
    data.setdefault("patients", [])
    data.setdefault("assignments", [])
    data.setdefault("sessions", [])
    data.setdefault("chat_logs", [])
    data.setdefault("kakao_sessions", {})
    data.setdefault("video_jobs", {})
    return data


def get_patients(path):
    store = load_store(path)
    return store["patients"]


def get_patient(path, patient_id):
    store = load_store(path)
    return next((p for p in store["patients"] if p["id"] == patient_id), None)


def get_patient_assignments(path, patient_id):
    store = load_store(path)
    return [a for a in store["assignments"] if a.get("patient_id") == patient_id]


def get_patient_sessions(path, patient_id):
    store = load_store(path)
    return [s for s in store["sessions"] if s.get("patient_id") == patient_id]


def save_assignments(path, assignments):
    store = load_store(path)
    store["assignments"] = assignments
    _write(path, store)


def save_patient_assignments(path, patient_id, assignments):
    store = load_store(path)
    other = [a for a in store["assignments"] if a.get("patient_id") != patient_id]
    for a in assignments:
        a["patient_id"] = patient_id
    store["assignments"] = other + assignments
    _write(path, store)


def append_session(path, session):
    store = load_store(path)
    store["sessions"].append(session)
    _write(path, store)


def append_chat_log(path, entry):
    store = load_store(path)
    store["chat_logs"].append(entry)
    _write(path, store)


def get_patient_chat_logs(path, patient_id, limit=None):
    store = load_store(path)
    logs = [c for c in store["chat_logs"] if c.get("patient_id") == patient_id]
    logs.sort(key=lambda c: c.get("timestamp", ""))
    if limit is not None:
        logs = logs[-limit:] if limit else []
    return logs


def find_patient_by_registration(path, name, registration_number):
    """이름 + 등록번호(4자리)로 환자를 찾는다. 이미 다른 카카오 계정에 연결됐어도 찾아준다."""
    store = load_store(path)
    return next(
        (
            p for p in store["patients"]
            if p.get("name") == name and p.get("registration_number") == registration_number
        ),
        None,
    )


def get_patient_by_kakao_id(path, kakao_user_id):
    store = load_store(path)
    return next((p for p in store["patients"] if p.get("kakao_user_id") == kakao_user_id), None)


def link_kakao_user(path, patient_id, kakao_user_id):
    """환자를 카카오 사용자 ID에 연결한다. 이미 그 patient_id를 쓰던 다른 kakao_user_id는 해제한다."""
    store = load_store(path)
    for p in store["patients"]:
        if p.get("kakao_user_id") == kakao_user_id and p["id"] != patient_id:
            p["kakao_user_id"] = None
        if p["id"] == patient_id:
            p["kakao_user_id"] = kakao_user_id
    _write(path, store)


def get_kakao_session(path, kakao_user_id):
    """카카오 사용자별 대화 상태(state machine)를 반환한다. 없으면 기본값."""
    store = load_store(path)
    return store["kakao_sessions"].get(kakao_user_id, {"state": "idle"})


def save_kakao_session(path, kakao_user_id, session_state):
    store = load_store(path)
    store["kakao_sessions"][kakao_user_id] = session_state
    _write(path, store)


def create_video_job(path, kakao_user_id, exercise_key, target_reps):
    """영상 백그라운드 분석 작업을 등록한다. 처음엔 status='pending'.

    문진(운동 전/후)이 진행되는 동안 백그라운드 스레드가 이 작업을 분석하고,
    끝나면 update_video_job으로 결과를 채운다. 반환값은 job_id.
    """
    store = load_store(path)
    job_id = uuid.uuid4().hex[:8]
    jobs = store["video_jobs"].setdefault(kakao_user_id, [])
    jobs.append({
        "job_id": job_id,
        "exercise_key": exercise_key,
        "target_reps": target_reps,
        "status": "pending",
        "pose_detected": None,
        "final_value": None,
    })
    _write(path, store)
    return job_id


def update_video_job(path, kakao_user_id, job_id, **fields):
    store = load_store(path)
    jobs = store["video_jobs"].get(kakao_user_id, [])
    for job in jobs:
        if job["job_id"] == job_id:
            job.update(fields)
    _write(path, store)


def get_video_jobs(path, kakao_user_id):
    store = load_store(path)
    return store["video_jobs"].get(kakao_user_id, [])


def clear_video_jobs(path, kakao_user_id):
    store = load_store(path)
    store["video_jobs"].pop(kakao_user_id, None)
    _write(path, store)


def generate_unique_patient_id(path):
    """기존 환자 id/registration_number와 겹치지 않는 5자리 숫자 문자열을 생성한다.

    모든 환자는 id와 registration_number를 동일한 5자리 고유번호로 통일한다(설계 확정,
    2026-08-06) — 카톡 신원확인과 내부 식별자를 같은 값으로 써서 관리 부하를 줄인다.
    기존 데모 환자(p1~p5)도 이 형식으로 일괄 마이그레이션됐다.
    """
    store = load_store(path)
    existing = {p["id"] for p in store["patients"]} | {
        p.get("registration_number") for p in store["patients"] if p.get("registration_number")
    }
    while True:
        candidate = f"{random.randint(10000, 99999)}"
        if candidate not in existing:
            return candidate


def add_patient(path, name, age, diagnosis, joint=None):
    """신규 환자를 등록한다. id와 registration_number는 동일한 5자리 고유번호로 발급된다."""
    unique_id = generate_unique_patient_id(path)
    store = load_store(path)
    patient = {
        "id": unique_id,
        "name": name,
        "age": age,
        "diagnosis": diagnosis,
        "joint": joint,
        "registered_at": datetime.now().date().isoformat(),
        "registration_number": unique_id,
        "kakao_user_id": None,
    }
    store["patients"].append(patient)
    _write(path, store)
    return patient


def assign_patient_to_doctor(path, doctor_username, patient_id):
    """신규 등록한 환자를 주치의의 담당 환자 목록(users[].patient_ids)에 추가한다."""
    store = load_store(path)
    for u in store["users"]:
        if u.get("username") == doctor_username and u.get("role") == "doctor":
            patient_ids = u.setdefault("patient_ids", [])
            if patient_id not in patient_ids:
                patient_ids.append(patient_id)
    _write(path, store)


def _write(path, store):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
