"""store.json의 기존 데이터를 DynamoDB 테이블로 마이그레이션하는 스크립트."""

import json
import os
from decimal import Decimal

import boto3

REGION = "us-east-1"
STORE_PATH = os.path.join(os.path.dirname(__file__), "dashboard", "data", "store.json")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def decimal_default(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(str(value))
    return value


def clean_item(item):
    """None과 빈 문자열을 제거하고 숫자를 Decimal로 변환."""
    cleaned = {}
    for k, v in item.items():
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            cleaned[k] = v
        elif isinstance(v, int):
            cleaned[k] = Decimal(str(v))
        elif isinstance(v, float):
            cleaned[k] = Decimal(str(v))
        elif isinstance(v, list):
            cleaned[k] = [clean_value(i) for i in v]
        elif isinstance(v, dict):
            cleaned[k] = clean_item(v)
        else:
            cleaned[k] = v
    return cleaned


def clean_value(v):
    """리스트 내부의 값을 변환."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return Decimal(str(v))
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return clean_item(v)
    if isinstance(v, list):
        return [clean_value(i) for i in v]
    return v


def migrate():
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        store = json.load(f)

    # 1. Users
    print("Migrating Users...")
    table = dynamodb.Table("CareFlow-Users")
    for user in store.get("users", []):
        table.put_item(Item=clean_item(user))
    print(f"  -> {len(store.get('users', []))} users migrated")

    # 2. Patients
    print("Migrating Patients...")
    table = dynamodb.Table("CareFlow-Patients")
    for patient in store.get("patients", []):
        # id -> patient_id로 변환
        item = {**patient}
        if "id" in item:
            item["patient_id"] = item.pop("id")
        table.put_item(Item=clean_item(item))
    print(f"  -> {len(store.get('patients', []))} patients migrated")

    # 3. Assignments
    print("Migrating Assignments...")
    table = dynamodb.Table("CareFlow-Assignments")
    for assignment in store.get("assignments", []):
        if not assignment.get("patient_id"):
            continue
        table.put_item(Item=clean_item(assignment))
    print(f"  -> {len(store.get('assignments', []))} assignments migrated")

    # 4. Sessions
    print("Migrating Sessions...")
    table = dynamodb.Table("CareFlow-Sessions")
    for session in store.get("sessions", []):
        if not session.get("patient_id"):
            session["patient_id"] = "unknown"
        if not session.get("session_id"):
            continue
        table.put_item(Item=clean_item(session))
    print(f"  -> {len(store.get('sessions', []))} sessions migrated")

    # 5. Chat Logs
    print("Migrating Chat Logs...")
    table = dynamodb.Table("CareFlow-ChatLogs")
    for log in store.get("chat_logs", []):
        if not log.get("patient_id") or not log.get("timestamp"):
            continue
        table.put_item(Item=clean_item(log))
    print(f"  -> {len(store.get('chat_logs', []))} chat logs migrated")

    # 6. Kakao Sessions
    print("Migrating Kakao Sessions...")
    table = dynamodb.Table("CareFlow-KakaoSessions")
    for kakao_user_id, state in store.get("kakao_sessions", {}).items():
        item = {"kakao_user_id": kakao_user_id, **state}
        table.put_item(Item=clean_item(item))
    print(f"  -> {len(store.get('kakao_sessions', {}))} kakao sessions migrated")

    # 7. Video Jobs
    print("Migrating Video Jobs...")
    table = dynamodb.Table("CareFlow-VideoJobs")
    count = 0
    for kakao_user_id, jobs in store.get("video_jobs", {}).items():
        for job in jobs:
            item = {"kakao_user_id": kakao_user_id, **job}
            table.put_item(Item=clean_item(item))
            count += 1
    print(f"  -> {count} video jobs migrated")

    print("\nMigration complete!")


if __name__ == "__main__":
    migrate()
