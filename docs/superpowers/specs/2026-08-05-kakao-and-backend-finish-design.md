# 카카오 챗봇 + 백엔드 마무리 — 브레인스토밍 중간 정리

> **상태: 미완성 (일부 해결).** 이 문서는 승인된 최종 스펙이 아니라 브레인스토밍 도중 정리된 결정 사항 기록이다. 이전 세션에서 마지막 질문(Bedrock 사용 범위)에 대한 답 없이 종료됐으나, 후속 세션에서 (B) 전체 이전으로 확정됨 — 아래 "결정 완료" 섹션 참고. 이어서 작업할 때는 그 섹션의 "다음 단계"부터 진행할 것.

## 배경 / 왜 이 작업을 하나

환자 중 나이대나 기기 숙련도 때문에 웹 대시보드를 못 쓰는 사람들을 위해, 카카오톡 메시지만으로 신원확인·운동 안내·질문답변·영상 제출까지 끝낼 수 있게 만드는 게 목표. 여기에 더해 지금까지 미뤄뒀던 백엔드 정리 작업(Phase 3/4, `docs/superpowers/plans/2026-08-05-backend-priorities.md` 참고) 전체를 이번에 같이 마무리하기로 범위를 넓혔다.

## 확정된 범위 (전체 로드맵)

1. **데이터 모델 기반 작업** — 아래 "확정 결정 1" 참고
2. **카카오 A (신원확인 + 텍스트 대화)**
3. **카카오 B (영상 접수 + 분석)**
4. **환자별 폴더 + 시맨틱 검색 RAG** (신규 추가됨)
5. **AWS EC2 배포**
6. **정리** — 기존 계획서의 Phase 4 (죽은 엔드포인트 삭제)

2/3은 서로 다른 구현 계획으로 분리해서 진행(A 먼저, B는 A 위에 얹힘). 나머지도 각각 별도 계획 문서로 이어질 예정 — Phase 1/2때와 같은 방식.

## 확정 결정

### 1. 웹캠 세션 `patient_id` 누락 버그 (신규 발견, 범위에 포함하기로 확정)

`dashboard/data/store.json`의 실제 세션 기록을 열어보니 `main.py`가 생성한 세션 2건(`67ea840f`, `e7c82706`)에 `patient_id`가 아예 없었다. 원인:
- `main.py:112` `build_session_record()`가 `patient_id` 파라미터 자체를 받지 않음
- `dashboard/server.py`의 `/api/start-exercise`가 `main.py` 서브프로세스 호출 시 `--patient-id`를 안 넘김

**즉 지금도 실제 웹캠 운동 세션은 어느 환자 것인지 기록이 안 남고, `/api/patients/<id>/sessions`, `/api/patients/<id>/stats`, 배정 완료 체크에 전혀 안 잡힌다.** 카카오 영상 세션도 결국 같은 `sessions` 배열을 쓰므로, 이 버그를 먼저 고쳐야 카카오 쪽도 제대로 동작한다.

**수정 방향:**
- `main.py`의 `build_session_record()`에 `patient_id` 파라미터 추가
- `/api/start-exercise`가 `main.py` 서브프로세스 호출 시 `--patient-id` 인자로 전달
- `source` 필드 신규 추가: 웹캠 세션은 `"webcam"`, 카톡 영상은 `"kakao_video"`. 기존 세션엔 이 필드가 없으므로 읽을 때 `s.get("source", "webcam")`처럼 기본값 처리 필요

### 2. 환자 데이터 모델 확장

`patients` 배열에 필드 2개 추가:
- `registration_number` (문자열, 4자리 숫자) — **환자 등록 시 시스템이 자동 생성.** 기존 5명(p1~p5)에도 소급 부여 필요
- `kakao_user_id` (문자열, nullable) — 카톡에서 "이름 등록번호" 형식으로 신원확인 성공 시 연결됨. 초기값 `null`

### 3. `chat_logs` 채널 확장

Phase 2에서 이미 만든 `chat_logs` 저장 구조(`dashboard/data_store.py`의 `append_chat_log`/`get_patient_chat_logs`)를 그대로 재사용. `channel` 필드에 기존 `"web"` 외에 `"kakao"` 값 추가 — 카톡 텍스트 대화도 같은 배열에 쌓여서 웹/카톡 구분 없이 요약 가능해짐.

### 4. 카카오 B: 영상 처리는 "즉시 1건씩", 하루 배치 아님

**중요한 정정 — 처음 참고했던 문서(다른 환경에서 검증된 것으로 추정)는 "하루치 영상을 다 받은 뒤 한꺼번에 분석"하는 구조였는데, 사용자가 명시적으로 다르게 정정함:**

> "1개씩 영상 받고 분석하잖아 카운트나 운동이 제대로 된건지 안된거면 다시 찍으라 해야하고"

즉:
- 영상 하나가 도착하면 **그 즉시** (콜백 메커니즘으로 5초 응답 제한 우회) 분석
- 분석 결과에 따라 그 자리에서 안내 — 다음 운동 안내 또는 재촬영 요청
- **재촬영 판단 기준 (확정):** 포즈 인식이 아예 안 된 경우(영상 전체에서 사람이 인식 안 됨)에만 "다시 찍어주세요". **반복 횟수가 목표에 못 미치는 건 재촬영 사유가 아니고, 그냥 `target_reached: false`로 기록만 하고 다음 운동으로 넘어감.**
- 이 방식이 원래 문서의 "하루 마지막 영상까지 기다렸다가 배치 분석" 구조보다 콜백 5분 제한 리스크도 오히려 작음 (영상 1개 분량만 그 시간 안에 처리하면 됨)

### 5. 영상 분석 파이프라인 — 코드 재사용성 확인됨

`dashboard/pose_detector.py`를 직접 확인한 결과, 이미 `RunningMode.VIDEO`로 만들어져 있고 `detect(frame_bgr)`가 BGR 프레임 + 타임스탬프만 받는 구조 — **웹캠 실시간 캡처와 완전히 분리되어 있어서, 저장된 영상 파일에서 추출한 프레임을 그대로 넣어도 동작한다.** `squat_tracker.py` 등 운동별 트래커도 `.update(landmarks)` 하나로 상태를 누적하는 stateless-per-frame 구조라 웹캠/파일 구분 없이 재사용 가능.

**새로 만들어야 하는 것 (`dashboard/video_analyzer.py`, 아직 없음):**
- 영상 파일을 프레임 단위로 여는 iterator (`cv2.VideoCapture` 기반)
- 프레임 간 관절 이동량 비교로 "쉬는 구간" 판단 + 트리밍 후 새 영상 저장
- 분석 후 원본 다운로드 파일 삭제

### 6. 환자별 폴더 + 시맨틱 검색 RAG (신규 요구사항)

사용자 요구사항 원문: "카톡 챗봇이나 웹 챗봇에서 환자가 나눈 대화나 영상이나 내용은 환자당 폴더 만들어서 날짜별로 정리 되어야해 ... 주치의가 영상을 받거나 내용 물어보거나 하면 주치의 챗봇이 RAG를 그 폴더에 연결해서 바로 찾지"

확인 결과 **"진짜 의미 검색(임베딩+벡터 검색)"**을 원함 (단순 최근 파일 읽기 방식이 아님).

- 환자별·날짜별 폴더에 대화록(웹+카톡 `chat_logs`)과 세션 요약(운동 기록)을 정리
- 임베딩+벡터 검색으로 주치의 챗봇 질문과 관련된 내용만 골라서 컨텍스트에 포함 (지금 Phase 2의 `_build_doctor_chat_context`처럼 전체를 텍스트로 다 넣는 방식이 아니라, 관련도 높은 것만)
- 영상 자체는 임베딩 대상이 아니라, 세션 메타데이터(날짜/운동/횟수/달성여부)를 텍스트로 만들어 임베딩 — 관련 세션을 찾으면 이미 있는 `video_path`/`/api/video/<session_id>`로 재생 링크 제공

### 7. AWS 배포

**EC2 인스턴스 1대** (Elastic Beanstalk 대안 검토했으나 EC2로 확정) — Flask 단일 프로세스를 systemd로 상시 실행, 카카오 스킬 URL이 HTTPS 필수라 앞단에 리버스 프록시(Nginx 등) 필요할 것으로 예상 (세부 미정).

## 결정 완료 (2026-08-06 후속 세션)

**Bedrock 사용 범위: (B) 확정 — LLM 대화 생성까지 전부 Bedrock으로 이전.**

AWS 계정 구조 확인 결과, 이 계정(`769456250598`, alias `axedu03`)은 해커톤 주최 측이 관리하는 AWS Organizations의 멤버 계정이고 결제수단도 주최 측 소유로 확인됨(개인 카드 아님). Bedrock 모델 접근 권한(`converse`, Titan 임베딩)도 실제 호출로 검증 완료.

결정 근거: 해커톤 심사에서 AWS 서비스 활용도가 중요한 평가 기준일 가능성이 높아, 크레딧 절약보다 "실제 프로덕션 경로에 Bedrock을 쓰고 있다"는 점이 우선한다고 판단. 단, 크레딧이 여러 팀과 공유되는 풀일 수 있으므로 완전히 무시하지는 않고 모델 선택으로 비용을 조절하기로 함.

- **챗봇 대화 생성 모델:** `anthropic.claude-haiku-4-5` (inference profile, `us.anthropic.claude-haiku-4-5-...` 형태로 호출). 환자용 "새싹이" 챗봇은 공감 표현이 중요해 한국어 품질을 우선시함 — Nova Lite/Micro보다 비싸지만 Sonnet/Opus보다는 훨씬 저렴한 선에서 절충.
- **RAG(6번) 임베딩:** `amazon.titan-embed-text-v2:0` (호출 테스트 성공, 저렴).
- **RAG(6번) 벡터 저장:** Bedrock Knowledge Bases(관리형)는 쓰지 않고, Titan 임베딩 API + **S3 Vectors**를 직접 호출하는 커스텀 RAG로 구현 — Knowledge Bases의 백그라운드 동기화 비용과 OpenSearch Serverless 시간당 최소 요금을 피하기 위함. S3 Vectors는 `us-east-1`에서 접근 가능 확인됨(현재 버킷 0개).
- **EC2 배포(7번):** `t3.micro`/`t2.micro` 프리티어 사양으로 최소화. 데모 종료 후 인스턴스는 stop(삭제 아님).

**후속 작업(설계 확정에 따라 신규 추가):** Phase 2에서 만든 `dashboard/llm_client.py`(Groq 기반)를 Bedrock(`boto3` + `converse` API) 기반으로 마이그레이션. `generate_reply(system_prompt, user_message) -> str` 시그니처는 유지하므로 호출부(`/api/chat`, `/api/doctor/chat`)는 수정 불필요. `requirements.txt`에서 `groq` 제거, `boto3` 추가. `.env`의 `GROQ_API_KEY` 의존성 제거(AWS 자격증명은 `~/.aws/credentials` 사용). `tests/test_llm_client.py`의 Groq mock을 `boto3` client mock으로 교체. 이 마이그레이션은 별도 계획 문서로 상세화할 것.

**비용 관리:** 크레딧이 주최 측 공유 풀일 가능성이 있어 AWS Budgets로 임계값 알림을 걸어두기로 함(진행 중 — 알림 수신 이메일 확정 필요).

**다음 단계:** 위 결정에 따라 6번(RAG) 기술 스택이 확정됐으니, 1번(웹캠 세션 `patient_id` 누락 버그, AWS 무관)부터 순서대로 각 단계를 Phase 1/2 때와 같은 방식(브레인스토밍 승인 → `writing-plans`로 상세 계획 → `subagent-driven-development`로 구현)으로 진행한다.
