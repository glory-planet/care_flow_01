# Care Flow

카카오톡 챗봇 + 웹 대시보드 기반 재활운동 관리 서비스. 환자는 카카오톡으로 신원확인, 문진, 운동 안내를 받고 운동 영상을 제출하며, 주치의는 웹 대시보드에서 환자 목록·문진 결과·운동 수행 기록을 확인한다.

## 배포 현황

- **서버**: AWS EC2 (t3.small), Elastic IP, `https://52-206-206-111.sslip.io` (Let's Encrypt HTTPS, 자동 갱신)
- **구성**: nginx(reverse proxy) → gunicorn → Flask(`dashboard/server.py`), systemd(`careflow.service`)로 상시 구동
- **LLM**: Amazon Bedrock, Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`)
- **병원 정보 RAG**: Amazon Bedrock Titan Embed v2 + S3 Vectors (`careflow-hospital-rag` 버킷, `patients` 인덱스). 등록 시 5자리 고유 ID로 병원 데모 데이터를 정확 매칭 조회

## 주요 기능

### 카카오톡 챗봇
- 신원확인(5자리 고유 ID로 환자 매칭)
- 일일 문진(1~10점 척도, 매우낮음/매우높음)
- 운동 안내 및 영상 제출 접수(백그라운드 분석 콜백)
- Bedrock 기반 자연어 대화(환자용/주치의용)

### 웹 대시보드 (`dashboard/`)
- 주치의 화면(`doctor.html`): 담당 환자 목록, 환자별 상세, 신규 환자 등록(병원 RAG 조회 자동완성), 운동 배정
- 환자 화면(`patient.html`): 배정된 운동 목록, 웹캠 기반 운동 수행(`main.py` + MediaPipe Pose)
- 환자 상세(`patient-detail.html`): 세션 기록, 문진 이력

### 운동 추적 (`*_tracker.py`)
MediaPipe Pose 기반 관절 각도 계산(`angle_calculator.py`)으로 8종 운동(스쿼트, 만세, 사이드레그레이즈, 오버헤드리치 등)의 반복 횟수·자세를 실시간 카운트. 저장된 영상 파일 분석은 `video_analyzer.py`가 동일 트래커 로직을 재사용.

## 데이터 모델

- `dashboard/data_store.py`: 환자/의사/배정/세션/문진/채팅로그를 `dashboard/data/store.json`에 저장하는 경량 저장소
- 환자 내부 ID == 카카오톡 신원확인용 고유번호 (5자리 숫자, 통일)

## 개발/실행

```bash
pip install -r requirements.txt
python -m dashboard.server        # 로컬 개발 서버 (Flask)
pytest                            # 테스트 (142개)
```

AWS 자격증명은 `~/.aws/credentials` 사용(Bedrock, S3 Vectors 호출용). 로컬 웹캠 없이는 `main.py`의 실시간 운동 추적 기능은 동작하지 않는다(카카오톡 영상 제출 경로는 무관).

## 진행 이력

- EC2 배포, HTTPS 적용, nginx+gunicorn+systemd 구동
- 죽은 엔드포인트 정리, `patient_id` 버그 수정
- 카카오톡 신원확인+문진+운동안내(A), 영상접수+백그라운드분석+콜백(B) 구현
- 병원 정보 RAG(S3 Vectors) 구축 및 신규 환자 등록 기능
- LLM을 Groq에서 Amazon Bedrock으로 마이그레이션
- 환자 ID/카카오톡 신원확인 번호를 5자리 고유번호로 통일(기존 환자 데이터 마이그레이션 포함)
- 데모용 환자 세션 데이터 백필

## 라이선스

내부 해커톤/데모 프로젝트.
