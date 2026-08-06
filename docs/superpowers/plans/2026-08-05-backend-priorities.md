# Care Flow 백엔드 정리 및 확장 — 우선순위 기획 문서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Phase 1 is complete (merged to master, commit `1ee37bf`).** Phase 2 is next.

**Goal:** FE(`dashboard/*.html`)가 실제로 호출하는 API를 기준으로 백엔드 갭을 메우고, FE에 하드코딩된 가짜 AI 요약/챗봇 응답을 실제 서버 로직으로 교체한다.

**Architecture:** 기존 Flask 단일 앱(`dashboard/server.py`) + JSON 파일 저장소(`dashboard/data/store.json`) 구조를 그대로 유지한다. 새 DB나 새 서버는 도입하지 않는다.

**Tech Stack:** Flask, `dashboard/data_store.py`의 JSON 저장소 함수, pytest (`tests/test_server.py` 패턴 재사용).

## Global Constraints

- 저장소는 `dashboard/data/store.json` 하나뿐이다 (별도 `patients.json`, DB 없음) — `dashboard/data_store.py:4`
- 인증은 세션 기반, 역할은 `doctor`/`patient` 두 가지뿐이다 — `dashboard/server.py:82-97`
- 모든 신규 API는 기존 테스트 픽스처 패턴(`tests/test_server.py:12-18`, `tmp_path` + `monkeypatch`로 `STORE_PATH` 격리)을 따른다.
- FE가 실제로 호출하지 않는 엔드포인트는 새로 만들지 않는다 — 아래 "FE 실사용 API 감사" 참고.
- **(Phase 2 확정 사항, 2026-08-05 → 2026-08-06 Bedrock으로 마이그레이션 완료)** LLM 제공자는 AWS Bedrock, 모델 `us.anthropic.claude-haiku-4-5-20251001-v1:0` (converse API). LLM 호출부는 `dashboard/llm_client.py`의 `generate_reply(system_prompt, user_message) -> str` 함수 하나로만 감싸고, 다른 파일에서 `boto3` bedrock-runtime 클라이언트를 직접 만들지 않는다.
- **(Phase 2 확정 사항 → 폐기)** API 키를 `.env` + `python-dotenv`로 관리하던 방식은 Bedrock 마이그레이션으로 폐기됨. 인증은 EC2 인스턴스 프로파일(IAM 역할, `bedrock:Converse` 권한)로 처리하며, 별도 API 키/`.env` 파일이 필요 없다.
- **(Phase 2 확정 사항)** 챗봇은 라우트를 역할별로 분리한다 — 환자용 `POST /api/chat`, 주치의용 `POST /api/doctor/chat`. 주치의용은 `patient_id`를 선택적으로 받는다: 있으면 그 환자만, 없으면 로그인한 주치의의 담당 환자 전체(`session["user"]["patient_ids"]`)를 대상으로 요약해서 답한다.

---

## FE 실사용 API 감사 (2026-08-05 기준 grep 결과)

FE 4개 파일(`login.html`, `doctor.html`, `patient.html`, `patient-detail.html`) 전체에서 `fetch(` 호출을 전수 조사한 결과:

**FE가 실제로 호출하는 것 (전부 백엔드에 이미 있음):**
`/api/login`, `/api/logout`, `/api/me`, `/api/doctor/patients-summary`, `/api/patients/<id>`, `/api/patients/<id>/sessions`, `/api/patients/<id>/assignments` (GET/POST), `/api/start-exercise`, `/api/video/<session_id>`

**백엔드엔 있는데 FE는 아무도 호출 안 함 (죽은 코드 후보):**
- `/api/verify-pin` — PIN 확인 로직 자체가 로그인 방식으로 대체된 것으로 보임 (`login.html`이 PIN이 아니라 아이디/비번 사용)
- `/api/assignments` (전역, patient_id 없는 버전) — `/api/patients/<id>/assignments`로 대체된 것으로 보임
- `/api/patients/<id>/stats` — 만들어져 있지만 아무도 안 부름. 대신 `patient-detail.html`이 세션/배정 원본 데이터를 받아 **JS에서 직접 재계산**하고 있음 (아래 Phase 1 참고)
- `/api/stretch-reminder/{status,start,stop}` — 대시보드 화면에 토글 UI가 없음. `stretch_reminder.py`는 실제로 존재하는 앱이라 완전히 죽은 기능은 아니고, "FE 연결이 안 된 상태"

**FE엔 UI가 있는데 백엔드가 아예 없음 (지금까지 전부 하드코딩):**
- 챗봇 (`patient.html:574-591`, `doctor.html`, `patient-detail.html`) — `sendMessage()`가 랜덤 응답 배열에서 고르거나(patient) 완전 미구현. 실제 LLM 호출 없음.
- AI 종합 요약 (`patient-detail.html:482-487`) — 클라이언트에서 출석률/달성률 직접 계산 후 문자열 템플릿으로 조립. 서버 왕복 없음.
- 챗봇 요약 (`patient-detail.html:490-497`) — **완전히 하드코딩된 고정 문자열.** 실제 대화 로그도 없고 요약 로직도 없음.
- 영상 요약 (`patient-detail.html:500-502`) — 세션 개수만 세고 나머지는 하드코딩 문장.
- 문진(설문) 요약/그래프 — 실제 문진 데이터를 받는 입력 경로가 어디에도 없음 (카톡이든 웹이든). `renderSurveyChart`가 무엇을 그리는지도 데이터 출처 확인 필요.

---

## 우선순위

| 순위 | 항목 | 이유 | 블로커 |
|---|---|---|---|
| **P0** | `patient-detail.html`의 출석률/달성률 중복 계산 제거 → 기존 `/api/patients/<id>/stats` 연결 | 이미 만들어진 엔드포인트가 있는데 FE가 안 씀. 로직도 미묘하게 다름(주간 정의가 서버는 "이번 주 월~오늘", FE는 "최근 롤링 7일") → 지금 둘이 다른 숫자를 낼 수 있는 버그 상태 | 없음 — 바로 착수 가능 |
| **P1** | `ai-summary` 하드코딩 제거 → 서버가 실제 통계 기반 요약 문장 생성 | P0와 같은 데이터 사용, LLM 없이 템플릿으로도 가치 있음 | 없음 |
| **P2** | 챗봇 실제 연동 (`/api/chat`, `/api/doctor/chat`) | 가장 눈에 띄는 가짜 기능, FE 3곳에 UI 이미 있음 | 없음 — 결정 완료(Groq, `.env`, 라우트 분리), 착수 가능 |
| **P3** | 챗봇 요약 / 영상 요약 실제 데이터화 | P2(챗봇이 실제로 로그를 쌓아야 요약할 거리가 생김)에 의존 | P2 완료 후 |
| **P4** | 죽은 엔드포인트 정리 (`/api/verify-pin`, 전역 `/api/assignments`) | 코드 정리, 혼란 방지 | 삭제 전 실제로 아무도 안 쓰는지 최종 확인 필요 (사용자 확인) |

**Phase 1(P0+P1)은 완료, master에 병합됨.** Phase 2(P2)는 아래에 bite-size 태스크로 정리했다. P3~P4는 Phase 2 완료 후 별도 계획 문서로 이어서 작성한다.

---

## Phase 1 (P0 + P1): 진짜 통계 API로 통일하고 요약 문장 서버에서 생성

### File 구조

- Modify: `dashboard/server.py` — `/api/patients/<patient_id>/stats` 응답에 `attendance` 필드(활동일수 기반, FE와 동일 정의로 통일)와 `summary` 필드(템플릿 문장) 추가
- Modify: `dashboard/patient-detail.html` — 클라이언트 재계산 로직 제거, `/api/patients/<id>/stats` 호출로 교체
- Test: `tests/test_server.py` — 새 필드 검증 테스트 추가

### Task 1: `/api/patients/<patient_id>/stats`에 `attendance`(활동일 기준 출석률) 추가

현재 서버의 `weekly.rate`는 "배정 운동 목표 달성률"이고, FE가 원하는 "출석률"(activeDays/7, 세션이 하루라도 있으면 출석)은 서버에 없는 별개 지표다. 두 지표를 각각 명확히 분리해서 추가한다.

**Files:**
- Modify: `dashboard/server.py:246-297` (`get_patient_stats`)
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `GET /api/patients/<patient_id>/stats` 응답에 최상위 키 `attendance: {"active_days": int, "total_days": int, "rate": int}` 추가 (주간 기준, 최근 7일 rolling — `patient-detail.html`이 쓰던 정의와 동일하게 맞춤)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_server.py::test_patient_stats_includes_attendance_rate -v`
Expected: FAIL — `KeyError: 'attendance'`

- [ ] **Step 3: 서버에 `attendance` 계산 추가**

`dashboard/server.py`의 `get_patient_stats` 함수(라인 246 부근) 안, `week_total, week_achieved = count_for_range(week_start, today)` 다음 줄에 추가:

```python
    rolling_start = today - timedelta(days=6)
    active_days = len({
        s.get("ended_at", "")[:10] for s in sessions
        if rolling_start.isoformat() <= s.get("ended_at", "")[:10] <= today.isoformat()
    })
```

그리고 함수 마지막 `return jsonify({...})` 블록에 키 추가:

```python
        "attendance": {
            "active_days": active_days,
            "total_days": 7,
            "rate": round(active_days / 7 * 100),
        },
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py::test_patient_stats_includes_attendance_rate -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add dashboard/server.py tests/test_server.py
git commit -m "feat: add rolling-week attendance rate to patient stats endpoint"
```

(주: 이 프로젝트는 아직 git 저장소가 아님 — 커밋 전에 `git init` 필요 여부를 사용자에게 먼저 확인할 것.)

### Task 2: `/api/patients/<patient_id>/stats`에 `summary` 문장 필드 추가 (템플릿 기반, LLM 없음)

`patient-detail.html:482-487`에 있던 하드코딩 문장 생성 로직을 서버로 옮긴다. LLM 없이 지금 있는 규칙(달성률 구간별 메시지)만 그대로 서버 함수로 이식 — Phase 2에서 LLM으로 교체 가능하게 함수를 분리해둔다.

**Files:**
- Modify: `dashboard/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1이 계산한 `active_days`, `total_days`, `week_achieved`, `week_total`
- Produces: `build_stats_summary(active_days, total_days, achieve_rate) -> str` 함수 (다음 Phase에서 LLM 버전으로 교체될 지점), `/api/patients/<patient_id>/stats` 응답에 최상위 키 `summary: str` 추가

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_build_stats_summary_high_achievement():
    from dashboard.server import build_stats_summary
    text = build_stats_summary(active_days=6, total_days=7, achieve_rate=90)
    assert "출석률 86%" in text
    assert "목표 달성이 우수합니다" in text


def test_build_stats_summary_low_achievement():
    from dashboard.server import build_stats_summary
    text = build_stats_summary(active_days=2, total_days=7, achieve_rate=30)
    assert "출석 독려가 필요합니다" in text
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_server.py -k build_stats_summary -v`
Expected: FAIL — `ImportError: cannot import name 'build_stats_summary'`

- [ ] **Step 3: 함수 구현**

`dashboard/server.py`에 `get_patient_stats` 함수 앞에 추가:

```python
def build_stats_summary(active_days, total_days, achieve_rate):
    attend_rate = round(active_days / total_days * 100) if total_days > 0 else 0
    tail = (
        "목표 달성이 우수합니다." if achieve_rate >= 80 else
        "꾸준히 참여하고 있으나 목표 미달성이 확인됩니다." if achieve_rate >= 50 else
        "출석 독려가 필요합니다."
    )
    return (
        f"이번 주 출석률 {attend_rate}%({active_days}/{total_days}일). "
        f"배정 운동 달성률은 {achieve_rate}%입니다. {tail}"
    )
```

`get_patient_stats`의 반환 `jsonify({...})`에 추가:

```python
        "summary": build_stats_summary(active_days, 7, week_achieved and round(week_achieved / week_total * 100) or 0),
```

(주: `week_total`이 0일 때 0으로 나눠지지 않도록 기존 `week_total > 0` 가드를 그대로 재사용할 것 — 위 식은 예시이니 실제 구현 시 기존 `round(week_achieved / week_total * 100) if week_total > 0 else 0` 패턴을 그대로 쓴다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -k build_stats_summary -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add dashboard/server.py tests/test_server.py
git commit -m "feat: generate rule-based weekly summary text server-side"
```

### Task 3: `patient-detail.html`이 클라이언트 재계산 대신 `/api/patients/<id>/stats` 사용하도록 교체

**Files:**
- Modify: `dashboard/patient-detail.html:425-506` (`renderSummaryTab`)

**Interfaces:**
- Consumes: Task 1/2가 만든 `GET /api/patients/<id>/stats` 응답의 `attendance.rate`, `attendance.active_days`, `attendance.total_days`, `summary`

- [ ] **Step 1: `init()`에서 stats도 함께 fetch**

`patient-detail.html:399-405`의 `Promise.all` 호출에 세 번째 fetch 추가:

```javascript
  const [sessRes, assignRes, statsRes] = await Promise.all([
    fetch(`/api/patients/${patientId}/sessions`),
    fetch(`/api/patients/${patientId}/assignments`),
    fetch(`/api/patients/${patientId}/stats`),
  ]);
  allSessions = await sessRes.json();
  assignments = await assignRes.json();
  patientStats = await statsRes.json();
```

파일 상단 `let allSessions = []; let assignments = [];` 다음 줄에 `let patientStats = {};` 선언 추가.

- [ ] **Step 2: `renderSummaryTab`의 468-487 라인(재계산 블록)을 서버 값 사용으로 교체**

```javascript
  document.getElementById('ai-summary').textContent = patientStats.summary || '';
```

이 한 줄이 기존 `totalDays`/`activeDays`/`totalReached`/`attendRate`/`achieveRate` 계산 블록과 `document.getElementById('ai-summary').textContent = ...` 템플릿 문자열 전체를 대체한다. 출석 테이블(434-466라인, `att-header`/`att-body`)은 일별 상세 뱃지라 서버 stats에 없는 정보이므로 그대로 둔다.

- [ ] **Step 3: 브라우저에서 수동 확인**

서버 재시작 후 `http://127.0.0.1:5000/doctor/patient/p1` 접속 → "AI 종합 요약" 텍스트가 서버에서 온 문장으로 뜨는지, 기존과 동일한 톤인지 확인.

- [ ] **Step 4: 커밋**

```bash
git add dashboard/patient-detail.html
git commit -m "refactor: consume server-computed stats instead of client-side recalculation"
```

---

## Phase 2 (P2): 챗봇 실제 연동

**결정 사항 (2026-08-05):**
- LLM: Groq, 모델 `llama-3.3-70b-versatile`. 나중에 Bedrock으로 옮길 예정이라 호출부는 `dashboard/llm_client.py` 하나로 감싼다.
- API 키: `.env` + `python-dotenv`.
- 라우트 분리: `POST /api/chat`(환자, 컴패니언 톤 "새싹이") / `POST /api/doctor/chat`(주치의, 데이터 조회 톤). 후자는 `patient_id`가 있으면 그 환자만, 없으면(`doctor.html` 목록 페이지에서 호출하는 경우) 담당 환자 전체를 요약해서 답한다.
- 주치의 챗봇 질의/응답은 `chat_logs`에 기록하지 않는다 — Phase 3의 "챗봇 요약" 기능은 환자-챗봇 대화(환자가 통증을 언급하는 등)를 주치의가 검토하는 기능이라, 환자 채널(`channel: "web"`, 환자 역할)만 로그를 쌓는다. 이 범위 밖으로 넓히지 않는다(YAGNI).

### File 구조

- Create: `dashboard/llm_client.py` — Groq 호출을 감싸는 단일 함수
- Create: `.env.example`
- Modify: `.gitignore` — `.env` 추가
- Modify: `requirements.txt` — `groq`, `python-dotenv` 추가
- Modify: `dashboard/data_store.py` — `chat_logs` 저장/조회 함수 추가
- Modify: `dashboard/server.py` — `/api/chat`, `/api/doctor/chat` 라우트 추가
- Modify: `dashboard/patient.html`, `dashboard/doctor.html`, `dashboard/patient-detail.html` — 가짜 `sendMessage()`를 실제 fetch로 교체
- Test: `tests/test_llm_client.py`(신규), `tests/test_data_store.py`, `tests/test_server.py`

### Task 4: `dashboard/llm_client.py` — Groq 호출 단일 진입점 + 환경 설정

**Files:**
- Create: `dashboard/llm_client.py`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `requirements.txt`
- Test: `tests/test_llm_client.py` (신규)

**Interfaces:**
- Produces: `generate_reply(system_prompt: str, user_message: str) -> str` — Task 6/7이 이 함수 하나만 import해서 쓴다. 다른 파일에서 `groq` 패키지를 직접 import하지 않는다.

- [ ] **Step 1: 의존성 추가**

`requirements.txt`에 추가:

```
groq
python-dotenv
```

설치: `pip install groq python-dotenv`

- [ ] **Step 2: `.env.example` 생성**

`.env.example` (프로젝트 루트):

```
GROQ_API_KEY=your-groq-api-key-here
```

`.gitignore`에 `.env` 한 줄 추가 (실제 키가 든 `.env`는 커밋되지 않게).

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_llm_client.py` (신규 파일):

```python
from unittest.mock import MagicMock, patch

from dashboard.llm_client import generate_reply


def test_generate_reply_calls_groq_with_system_and_user_message(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "안녕하세요, 좋은 하루 보내세요!"

    with patch("dashboard.llm_client.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = fake_response
        reply = generate_reply("당신은 친절한 재활 코치입니다.", "오늘 스쿼트 몇 개 해야 하나요?")

    assert reply == "안녕하세요, 좋은 하루 보내세요!"
    MockGroq.assert_called_once_with(api_key="test-key")
    call_kwargs = MockGroq.return_value.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "당신은 친절한 재활 코치입니다."},
        {"role": "user", "content": "오늘 스쿼트 몇 개 해야 하나요?"},
    ]
```

- [ ] **Step 4: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.llm_client'`

- [ ] **Step 5: 구현**

`dashboard/llm_client.py` (신규 파일):

```python
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


def generate_reply(system_prompt, user_message):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return completion.choices[0].message.content
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add dashboard/llm_client.py .env.example .gitignore requirements.txt tests/test_llm_client.py
git commit -m "feat: add single-entry-point Groq LLM client"
```

(주: 실제 `GROQ_API_KEY`가 든 `.env` 파일은 사용자가 로컬에서 직접 만들어야 한다 — 이 태스크에서 만들거나 커밋하지 않는다.)

### Task 5: `chat_logs` 저장/조회

**Files:**
- Modify: `dashboard/data_store.py`
- Test: `tests/test_data_store.py`

**Interfaces:**
- Produces: `append_chat_log(path, entry)`, `get_patient_chat_logs(path, patient_id, limit=None) -> list`
- `load_store`의 기본 딕셔너리에 `"chat_logs": []` 키 추가 — 이미 있는 `test_load_store_missing_file_returns_defaults`, `test_load_store_corrupted_json_returns_defaults` 두 테스트의 기대값도 같이 업데이트해야 한다(안 그러면 이 태스크가 기존 테스트를 깨뜨림).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_data_store.py`에 추가 (파일 상단 import에 `append_chat_log`, `get_patient_chat_logs` 추가):

```python
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
```

그리고 기존 두 테스트를 이렇게 고친다:

```python
def test_load_store_missing_file_returns_defaults(tmp_path):
    path = str(tmp_path / "store.json")
    store = load_store(path)
    assert store == {"patients": [], "assignments": [], "sessions": [], "chat_logs": []}


def test_load_store_corrupted_json_returns_defaults(tmp_path):
    path = str(tmp_path / "store.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    store = load_store(path)
    assert store == {"patients": [], "assignments": [], "sessions": [], "chat_logs": []}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_data_store.py -v`
Expected: 새 테스트 2개는 `ImportError`, 기존 2개는 `AssertionError` (아직 `chat_logs` 키가 없어서)

- [ ] **Step 3: 구현**

**주의:** `load_store`에는 반환 지점이 3곳 있다 — (a) 파일이 없을 때(19번 줄 부근)의 하드코딩된 dict, (b) JSON 파싱 실패 시(25번 줄 부근)의 하드코딩된 dict, (c) 정상 로드 후 `setdefault` 세 줄(27-29번 줄). Phase 1 때 `patients` 키를 추가하면서 (a)/(b)를 놓쳐서 테스트가 깨졌던 것과 같은 실수를 반복하지 않도록, **세 곳 모두** 고친다:

`dashboard/data_store.py`의 `load_store` 함수 전체를 아래로 교체:

```python
def load_store(path):
    if not os.path.exists(path):
        return {"patients": [], "assignments": [], "sessions": [], "chat_logs": []}

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"patients": [], "assignments": [], "sessions": [], "chat_logs": []}

    data.setdefault("patients", [])
    data.setdefault("assignments", [])
    data.setdefault("sessions", [])
    data.setdefault("chat_logs", [])
    return data
```

파일 끝(`_write` 함수 앞)에 추가:

```python
def append_chat_log(path, entry):
    store = load_store(path)
    store["chat_logs"].append(entry)
    _write(path, store)


def get_patient_chat_logs(path, patient_id, limit=None):
    store = load_store(path)
    logs = [c for c in store["chat_logs"] if c.get("patient_id") == patient_id]
    logs.sort(key=lambda c: c.get("timestamp", ""))
    if limit is not None:
        logs = logs[-limit:]
    return logs
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_data_store.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add dashboard/data_store.py tests/test_data_store.py
git commit -m "feat: add chat_logs storage to data_store"
```

### Task 6: `POST /api/chat` — 환자용 챗봇 ("새싹이")

**Files:**
- Modify: `dashboard/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 4의 `generate_reply(system_prompt, user_message) -> str`, Task 5의 `append_chat_log`
- Produces: `POST /api/chat`, body `{"message": str}`, 응답 `{"reply": str}`. 로그인 세션의 `role == "patient"`만 허용(403), `patient_id`는 `session["user"]["patient_id"]`에서 가져온다(요청 바디에 없음 — 자기 자신 채팅이라 body에 patient_id를 받을 필요가 없다).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`에 추가 (파일 상단 import에 `append_chat_log` 등 필요 시 추가):

```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_server.py -k patient_chat -v`
Expected: FAIL — `404 NOT FOUND` (라우트가 아직 없음)

- [ ] **Step 3: 구현**

`dashboard/server.py` 상단 import 블록에 추가:

```python
from dashboard.data_store import (
    DEFAULT_STORE_PATH,
    append_chat_log,
    authenticate_user,
    get_patient,
    get_patient_assignments,
    get_patient_sessions,
    get_patients,
    load_store,
    save_assignments,
    save_patient_assignments,
)
from dashboard.llm_client import generate_reply
```

`get_patient_sessions_api` 함수 뒤, `build_stats_summary` 앞에 추가:

```python
PATIENT_CHAT_SYSTEM_PROMPT = (
    "당신은 재활 운동 앱 'Care Flow'의 컴패니언 캐릭터 '새싹이'입니다. "
    "환자를 따뜻하고 다정하게 격려하는 말투로 짧게 대답하세요. "
    "의학적 진단이나 처방은 하지 말고, 통증을 호소하면 주치의에게 전달하겠다고 안내하세요."
)


def _build_patient_chat_context(patient_id):
    sessions = get_patient_sessions(STORE_PATH, patient_id)
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent = [s for s in sessions if s.get("ended_at", "") >= cutoff]
    if not recent:
        return "최근 30일 운동 기록: 없음"
    lines = [
        f"- {s.get('ended_at', '')[:10]} "
        f"{EXERCISE_NAMES.get(s['exercise_key'], s['exercise_key'])} "
        f"{'목표 달성' if s.get('target_reached') else '목표 미달성'}"
        for s in recent
    ]
    return "최근 30일 운동 기록:\n" + "\n".join(lines)


@app.route("/api/chat", methods=["POST"])
def patient_chat():
    user = session.get("user")
    if not user or user["role"] != "patient":
        return jsonify({"error": "forbidden"}), 403

    message = request.get_json()["message"]
    patient_id = user["patient_id"]

    append_chat_log(STORE_PATH, {
        "patient_id": patient_id, "channel": "web", "role": "user",
        "message": message, "timestamp": datetime.now().isoformat(),
    })

    context = _build_patient_chat_context(patient_id)
    reply = generate_reply(f"{PATIENT_CHAT_SYSTEM_PROMPT}\n\n{context}", message)

    append_chat_log(STORE_PATH, {
        "patient_id": patient_id, "channel": "web", "role": "bot",
        "message": reply, "timestamp": datetime.now().isoformat(),
    })

    return jsonify({"reply": reply})
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -k patient_chat -v`
Expected: PASS

전체 스위트도 한 번 돌려서 회귀 없는지 확인: `python -m pytest tests/ -q`

- [ ] **Step 5: 커밋**

```bash
git add dashboard/server.py tests/test_server.py
git commit -m "feat: add POST /api/chat patient companion chatbot"
```

### Task 7: `POST /api/doctor/chat` — 주치의용 챗봇

**Files:**
- Modify: `dashboard/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 4의 `generate_reply`
- Produces: `POST /api/doctor/chat`, body `{"message": str, "patient_id": str | null}`, 응답 `{"reply": str}`. `role == "doctor"`만 허용(403). `patient_id`가 있으면 `session["user"]["patient_ids"]`에 포함돼야 함(아니면 403) — 이 검사는 Task 3(Phase 1)에서 만든 것과 동일한 패턴은 아니고, `doctor_patients_summary`가 담당 환자를 `patient_ids`로 필터링하는 것과 같은 방식이다. `patient_id`가 없으면 담당 환자 전체를 요약해서 컨텍스트로 넘긴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python -m pytest tests/test_server.py -k doctor_chat -v`
Expected: FAIL — `404 NOT FOUND`

- [ ] **Step 3: 구현**

`dashboard/server.py`의 `patient_chat` 함수 뒤에 추가:

```python
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

    data = request.get_json()
    message = data["message"]
    target_patient_id = data.get("patient_id")
    patient_ids = user.get("patient_ids") or []

    if target_patient_id and target_patient_id not in patient_ids:
        return jsonify({"error": "forbidden"}), 403

    context = _build_doctor_chat_context(patient_ids, target_patient_id)
    if context is None:
        return jsonify({"error": "patient not found"}), 404

    reply = generate_reply(f"{DOCTOR_CHAT_SYSTEM_PROMPT}\n\n{context}", message)
    return jsonify({"reply": reply})
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -k doctor_chat -v`
Expected: PASS

전체 스위트: `python -m pytest tests/ -q`

- [ ] **Step 5: 커밋**

```bash
git add dashboard/server.py tests/test_server.py
git commit -m "feat: add POST /api/doctor/chat assistant for single or all assigned patients"
```

### Task 8: FE 3곳의 가짜 `sendMessage()`를 실제 API 호출로 교체

**Files:**
- Modify: `dashboard/patient.html` (챗봇 `sendMessage()`, 대략 574-591라인 — 정확한 위치는 `function sendMessage()` 검색으로 찾을 것)
- Modify: `dashboard/doctor.html` (챗봇 `sendMessage()`)
- Modify: `dashboard/patient-detail.html` (두 번째 챗봇 — `chatbot-messages2`/`chatbot-input-field2` id를 쓰는 쪽의 `sendMessage()`)

**Interfaces:**
- Consumes: Task 6의 `POST /api/chat` (patient.html에서), Task 7의 `POST /api/doctor/chat` (doctor.html, patient-detail.html에서 — patient-detail.html은 이미 스코프에 있는 `patientId` 변수를 `patient_id`로 같이 보낸다)

- [ ] **Step 1: `patient.html`의 `sendMessage()` 교체**

기존 (랜덤 응답 `setTimeout` 블록)을 찾아서 전체를 아래로 교체:

```javascript
async function sendMessage() {
  const text = inputField.value.trim();
  if (!text) return;
  appendMsg('user', text);
  inputField.value = '';

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    appendMsg('bot', data.reply || '죄송해요, 지금은 답변할 수 없어요.');
  } catch (err) {
    appendMsg('bot', '죄송해요, 지금은 답변할 수 없어요.');
  }
}
```

`appendMsg` 함수와 이벤트 리스너 등록(`sendBtn.addEventListener(...)`, `inputField.addEventListener(...)`)은 그대로 둔다 — `sendMessage` 함수 본문만 교체.

- [ ] **Step 2: `doctor.html`의 `sendMessage()` 교체**

같은 패턴, `patient_id` 없이 `/api/doctor/chat` 호출:

```javascript
async function sendMessage() {
  const text = inputField.value.trim();
  if (!text) return;
  appendMsg('user', text);
  inputField.value = '';

  try {
    const res = await fetch('/api/doctor/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    appendMsg('bot', data.reply || '죄송합니다, 지금은 답변할 수 없습니다.');
  } catch (err) {
    appendMsg('bot', '죄송합니다, 지금은 답변할 수 없습니다.');
  }
}
```

- [ ] **Step 3: `patient-detail.html`의 두 번째 챗봇(`sendMessage`) 교체**

`chatbot-messages2`/`chatbot-input-field2`/`chatbot-send-btn2` id를 쓰는 `<script>` 블록을 찾는다. 이 파일은 최상위 스코프에 이미 `patientId`(URL에서 파싱한 값)와 `patientInfo`가 있으므로, 같은 패턴에 `patient_id: patientId`를 body에 추가:

```javascript
async function sendMessage() {
  const text = inputField.value.trim();
  if (!text) return;
  appendMsg('user', text);
  inputField.value = '';

  try {
    const res = await fetch('/api/doctor/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, patient_id: patientId }),
    });
    const data = await res.json();
    appendMsg('bot', data.reply || '죄송합니다, 지금은 답변할 수 없습니다.');
  } catch (err) {
    appendMsg('bot', '죄송합니다, 지금은 답변할 수 없습니다.');
  }
}
```

이 파일의 `msgContainer`가 `chatbot-messages2`를 가리키는 지역 변수를 쓰고 있을 것 — `appendMsg` 함수 본문(요소 생성 후 `msgContainer.appendChild`)은 건드리지 말고 `sendMessage` 함수 본문만 교체한다. 변수명이 설명과 다르면(예: 함수/변수 이름이 다르게 되어 있으면) 실제 파일 내용을 기준으로 판단하고, 애매하면 질문할 것.

- [ ] **Step 4: 서버 기동 후 검증**

브라우저 도구가 없으므로 Flask test client로 검증(Phase 1 Task 3와 같은 방식): 세 파일 각각이 문법 오류 없이 서빙되는지(`send_from_directory`로 200 응답), 그리고 `grep`으로 세 파일 모두에 더 이상 `setTimeout`이나 랜덤 응답 배열이 남아있지 않은지, `/api/chat` 또는 `/api/doctor/chat` fetch 호출이 정확히 들어갔는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add dashboard/patient.html dashboard/doctor.html dashboard/patient-detail.html
git commit -m "feat: wire chatbot UIs to real /api/chat and /api/doctor/chat endpoints"
```

## Phase 3 (P3, Phase 2 이후): 챗봇 요약 / 영상 요약 실데이터화

`chat_logs` 저장(Phase 2에서 구현)이 선행되어야 요약할 대화 데이터가 생긴다. 영상 요약은 세션의 `video_path`를 분석하는 별도 로직(현재 프로젝트엔 영상 분석 코드 없음 — mediapipe 기반 pose landmark 재분석 정도만 가능, "자세 정확도" 같은 평가지표는 새로 설계해야 함)이 필요해서 범위가 큼. 별도 계획 문서로 분리 권장.

## Phase 4 (P4): 죽은 엔드포인트 정리 — 완료 (2026-08-06)

`/api/verify-pin`, 전역 `/api/assignments`(GET/POST) 삭제. FE 어디서도 호출하지 않음을 grep으로 재확인 후 처리. `tests/test_server.py`의 `test_verify_pin_correct`, `test_verify_pin_incorrect`, `test_post_then_get_assignments`, `test_get_assignments_empty_by_default` 함께 제거. 부수적으로 더 이상 안 쓰이는 `DEMO_PIN`, `_today()` 도 함께 제거.

---

## Self-Review

- **스펙 커버리지:** FE 감사에서 나온 5개 갭(챗봇 3곳, AI 요약, 챗봇 요약, 영상 요약, 문진) 중 AI 요약은 Phase 1에서, 챗봇 3곳은 Phase 2에서 다룸. 챗봇 요약/영상 요약은 Phase 2가 쌓는 `chat_logs`에 의존해서 Phase 3으로 분리 — 의도된 범위 축소.
- **Placeholder 스캔:** Phase 1 Task 1~3, Phase 2 Task 4~8 전부 실제 코드 포함. Phase 3/4는 의도적으로 미상세화(Phase 2 완료 후 별도 계획) — Phase 1은 완료, Phase 2가 지금 실행 가능.
- **타입/시그니처 일관성:** `build_stats_summary(active_days, total_days, achieve_rate)`는 Phase 1 전체에서 동일. `generate_reply(system_prompt, user_message) -> str`이 Task 4에서 정의되고 Task 6/7이 동일 시그니처로 소비. `_build_patient_chat_context`/`_build_doctor_chat_context`/`_summarize_patient_for_doctor_chat` 헬퍼 이름이 Task 6/7 사이에서 충돌하지 않게 역할별로 접두사(`_build_patient_*` vs `_build_doctor_*`/`_summarize_patient_for_doctor_chat`)를 분리함.
- **Task 7의 `patient_id` 소유권 검사:** `target_patient_id not in patient_ids`로 막되, `patient_ids`가 `None`일 수 있는 기존 세션 스키마(`server.py:90-96`, 환자 로그인 시 `patient_ids`는 항상 `None`)를 고려해 `user.get("patient_ids") or []`로 방어함 — 이 부분은 Task 7 구현자가 실제 코드를 작성할 때 다시 한번 확인할 것.
