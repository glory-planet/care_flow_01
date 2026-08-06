"""DynamoDB 기반 데이터 저장소.

기존 JSON 파일(store.json) 기반에서 AWS DynamoDB로 전환한 모듈.
함수 시그니처는 기존과 동일하게 유지하되, path 매개변수는 하위 호환을 위해 받지만 무시한다.
"""

import random
import uuid
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

REGION = "us-east-1"

# 테이블 이름
TABLE_USERS = "CareFlow-Users"
TABLE_PATIENTS = "CareFlow-Patients"
TABLE_ASSIGNMENTS = "CareFlow-Assignments"
TABLE_SESSIONS = "CareFlow-Sessions"
TABLE_CHAT_LOGS = "CareFlow-ChatLogs"
TABLE_KAKAO_SESSIONS = "CareFlow-KakaoSessions"
TABLE_VIDEO_JOBS = "CareFlow-VideoJobs"

# 하위 호환 — 기존 코드에서 import하는 경로 유지
DEFAULT_STORE_PATH = "dynamodb"

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=REGION)
    return _dynamodb


def _table(name):
    return _get_dynamodb().Table(name)


def _to_python(item):
    """DynamoDB에서 가져온 Decimal을 int/float로 변환한다."""
    if item is None:
        return None
    if isinstance(item, list):
        return [_to_python(i) for i in item]
    if isinstance(item, dict):
        return {k: _to_python(v) for k, v in item.items()}
    if isinstance(item, Decimal):
        if item % 1 == 0:
            return int(item)
        return float(item)
    return item


def _to_dynamo(value):
    """Python 값을 DynamoDB 호환 타입으로 변환한다 (float→Decimal, None 제거)."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_to_dynamo(i) for i in value]
    return value


def _clean_item(item):
    """None 값과 빈 문자열을 제거한 DynamoDB 호환 아이템을 만든다."""
    cleaned = {}
    for k, v in item.items():
        if v is None or v == "":
            continue
        cleaned[k] = _to_dynamo(v)
    return cleaned


# --- 사용자 인증 (Cognito 전환 전 임시) ---

def authenticate_user(path, username, password):
    """username/password로 사용자를 인증한다. 성공 시 user dict, 실패 시 None."""
    table = _table(TABLE_USERS)
    response = table.get_item(Key={"username": username})
    user = response.get("Item")
    if user is None:
        return None
    user = _to_python(user)
    if user.get("password") != password:
        return None
    return user


# --- 환자 ---

def get_patients(path):
    table = _table(TABLE_PATIENTS)
    response = table.scan()
    return _to_python(response.get("Items", []))


def get_patient(path, patient_id):
    table = _table(TABLE_PATIENTS)
    response = table.get_item(Key={"patient_id": patient_id})
    item = response.get("Item")
    if item is None:
        return None
    result = _to_python(item)
    # 하위 호환: id 필드 유지
    result["id"] = result.get("patient_id", result.get("id"))
    return result


def find_patient_by_registration(path, name, registration_number):
    """이름 + 등록번호로 환자를 찾는다."""
    patients = get_patients(path)
    return next(
        (p for p in patients
         if p.get("name") == name and p.get("registration_number") == registration_number),
        None,
    )


def get_patient_by_kakao_id(path, kakao_user_id):
    patients = get_patients(path)
    return next((p for p in patients if p.get("kakao_user_id") == kakao_user_id), None)


def link_kakao_user(path, patient_id, kakao_user_id):
    """환자를 카카오 사용자 ID에 연결한다."""
    # 기존에 같은 kakao_user_id를 쓰던 다른 환자가 있으면 해제
    patients = get_patients(path)
    table = _table(TABLE_PATIENTS)
    for p in patients:
        if p.get("kakao_user_id") == kakao_user_id and p.get("patient_id", p.get("id")) != patient_id:
            table.update_item(
                Key={"patient_id": p.get("patient_id", p.get("id"))},
                UpdateExpression="REMOVE kakao_user_id",
            )
    # 대상 환자에 kakao_user_id 설정
    table.update_item(
        Key={"patient_id": patient_id},
        UpdateExpression="SET kakao_user_id = :kid",
        ExpressionAttributeValues={":kid": kakao_user_id},
    )


def generate_unique_patient_id(path):
    """기존 환자 id와 겹치지 않는 5자리 숫자 문자열을 생성한다."""
    patients = get_patients(path)
    existing = {p.get("patient_id", p.get("id")) for p in patients} | {
        p.get("registration_number") for p in patients if p.get("registration_number")
    }
    while True:
        candidate = f"{random.randint(10000, 99999)}"
        if candidate not in existing:
            return candidate


def add_patient(path, name, age, diagnosis, joint=None):
    """신규 환자를 등록한다."""
    unique_id = generate_unique_patient_id(path)
    table = _table(TABLE_PATIENTS)
    patient = {
        "patient_id": unique_id,
        "name": name,
        "age": age,
        "diagnosis": diagnosis,
        "joint": joint,
        "registered_at": datetime.now().date().isoformat(),
        "registration_number": unique_id,
    }
    table.put_item(Item=_clean_item(patient))
    # 하위 호환
    patient["id"] = unique_id
    return patient


def assign_patient_to_doctor(path, doctor_username, patient_id):
    """신규 등록한 환자를 주치의의 담당 환자 목록에 추가한다."""
    table = _table(TABLE_USERS)
    response = table.get_item(Key={"username": doctor_username})
    user = response.get("Item")
    if user is None or user.get("role") != "doctor":
        return
    patient_ids = list(user.get("patient_ids", []))
    if patient_id not in patient_ids:
        patient_ids.append(patient_id)
        table.update_item(
            Key={"username": doctor_username},
            UpdateExpression="SET patient_ids = :pids",
            ExpressionAttributeValues={":pids": patient_ids},
        )


# --- 배정 운동 ---

def get_patient_assignments(path, patient_id):
    table = _table(TABLE_ASSIGNMENTS)
    response = table.query(KeyConditionExpression=Key("patient_id").eq(patient_id))
    return _to_python(response.get("Items", []))


def save_assignments(path, assignments):
    """전체 배정을 덮어쓴다 (관리자 전체 저장용)."""
    table = _table(TABLE_ASSIGNMENTS)
    # 기존 전체 삭제 후 재등록
    scan = table.scan()
    with table.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(Key={"patient_id": item["patient_id"], "exercise_key": item["exercise_key"]})
    # 새 배정 등록
    with table.batch_writer() as batch:
        for a in assignments:
            batch.put_item(Item=_clean_item(a))


def save_patient_assignments(path, patient_id, assignments):
    """특정 환자의 배정 운동을 교체한다."""
    table = _table(TABLE_ASSIGNMENTS)
    # 해당 환자의 기존 배정 삭제
    existing = table.query(KeyConditionExpression=Key("patient_id").eq(patient_id))
    with table.batch_writer() as batch:
        for item in existing.get("Items", []):
            batch.delete_item(Key={"patient_id": patient_id, "exercise_key": item["exercise_key"]})
    # 새 배정 등록
    with table.batch_writer() as batch:
        for a in assignments:
            a["patient_id"] = patient_id
            batch.put_item(Item=_clean_item(a))


# --- 세션 (운동 수행 기록) ---

def get_patient_sessions(path, patient_id):
    table = _table(TABLE_SESSIONS)
    response = table.query(KeyConditionExpression=Key("patient_id").eq(patient_id))
    return _to_python(response.get("Items", []))


def append_session(path, session_record):
    table = _table(TABLE_SESSIONS)
    # patient_id가 없는 레거시 데이터 대응
    if not session_record.get("patient_id"):
        session_record["patient_id"] = "unknown"
    table.put_item(Item=_clean_item(session_record))


# --- 채팅 로그 ---

def append_chat_log(path, entry):
    table = _table(TABLE_CHAT_LOGS)
    if not entry.get("timestamp"):
        entry["timestamp"] = datetime.now().isoformat()
    # 같은 patient_id + timestamp가 겹치지 않도록 uuid 추가
    entry["timestamp"] = entry["timestamp"] + "_" + uuid.uuid4().hex[:6]
    table.put_item(Item=_clean_item(entry))


def get_patient_chat_logs(path, patient_id, limit=None):
    table = _table(TABLE_CHAT_LOGS)
    response = table.query(
        KeyConditionExpression=Key("patient_id").eq(patient_id),
        ScanIndexForward=True,  # 오래된 순
    )
    logs = _to_python(response.get("Items", []))
    if limit is not None and limit > 0:
        logs = logs[-limit:]
    return logs


# --- 카카오 세션 (상태머신) ---

def get_kakao_session(path, kakao_user_id):
    table = _table(TABLE_KAKAO_SESSIONS)
    response = table.get_item(Key={"kakao_user_id": kakao_user_id})
    item = response.get("Item")
    if item is None:
        return {"state": "idle"}
    return _to_python(item)


def save_kakao_session(path, kakao_user_id, session_state):
    table = _table(TABLE_KAKAO_SESSIONS)
    item = {"kakao_user_id": kakao_user_id, **session_state}
    table.put_item(Item=_clean_item(item))


# --- 영상 분석 작업 ---

def create_video_job(path, kakao_user_id, exercise_key, target_reps):
    table = _table(TABLE_VIDEO_JOBS)
    job_id = uuid.uuid4().hex[:8]
    item = {
        "kakao_user_id": kakao_user_id,
        "job_id": job_id,
        "exercise_key": exercise_key,
        "target_reps": target_reps,
        "status": "pending",
    }
    table.put_item(Item=_clean_item(item))
    return job_id


def update_video_job(path, kakao_user_id, job_id, **fields):
    table = _table(TABLE_VIDEO_JOBS)
    update_parts = []
    values = {}
    for i, (k, v) in enumerate(fields.items()):
        if v is None:
            continue
        attr_name = f":v{i}"
        update_parts.append(f"{k} = {attr_name}")
        values[attr_name] = _to_dynamo(v)
    if not update_parts:
        return
    table.update_item(
        Key={"kakao_user_id": kakao_user_id, "job_id": job_id},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeValues=values,
    )


def get_video_jobs(path, kakao_user_id):
    table = _table(TABLE_VIDEO_JOBS)
    response = table.query(KeyConditionExpression=Key("kakao_user_id").eq(kakao_user_id))
    return _to_python(response.get("Items", []))


def clear_video_jobs(path, kakao_user_id):
    table = _table(TABLE_VIDEO_JOBS)
    response = table.query(KeyConditionExpression=Key("kakao_user_id").eq(kakao_user_id))
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(Key={"kakao_user_id": kakao_user_id, "job_id": item["job_id"]})


# --- 하위 호환 함수 (server.py에서 load_store 호출하는 부분용) ---

def load_store(path=None):
    """하위 호환. server.py의 일부 로직에서 직접 store를 읽는 경우가 있다.
    DynamoDB에서 각 테이블을 조합해서 반환한다."""
    patients = get_patients(path)
    # id 필드 호환
    for p in patients:
        if "patient_id" in p and "id" not in p:
            p["id"] = p["patient_id"]

    # Assignments 전체 scan
    table = _table(TABLE_ASSIGNMENTS)
    assignments = _to_python(table.scan().get("Items", []))

    # Sessions 전체 scan
    table = _table(TABLE_SESSIONS)
    sessions = _to_python(table.scan().get("Items", []))

    return {
        "patients": patients,
        "assignments": assignments,
        "sessions": sessions,
    }
