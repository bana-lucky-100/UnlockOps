# UnlockOps

서비스 접근 문제를 진단하고, 지정 승인자의 승인 후 모의 SaaS에 권한을 부여하는 프로젝트입니다.
바탕화면 `mcp_project 2`의 코드를 기존 팀별 폴더 구조로 이식했습니다. 원본 폴더는 수정하지 않았습니다.

## 현재 구현 범위

- Vue 3 → Spring Boot → RabbitMQ → LangGraph worker → Policy MCP / Business MCP로 처리합니다.
- 한 요청은 한 플랫폼·한 자원만 처리합니다. S1-a~d는 독립 요청이며 S1 통합 승인 카드는 아직 없습니다.
- 정보 부족·복수 자원은 `MANUAL_REVIEW`, 예산 부족은 `REJECTED / BUDGET_INSUFFICIENT`로 종료합니다.
- 지정 승인자·계획 해시 검증, 승인 대기 체크포인트, 실행 키 기반 중복 방지, 부여 후 재조회를 유지합니다.
- Jira 실패 시 최초 실행을 포함해 총 3회 시도합니다. 여러 플랫폼의 부분 성공 처리는 아직 없습니다.
- 기본 `AGENT_MODE=demo`는 규칙 기반이며 유료 모델을 호출하지 않습니다. LLM 도구 선택은 `llm` 모드에서 동작합니다.
- 두 개의 독립 Agent가 구현된 상태는 아닙니다. 현재는 해석·조회·판정·승인·실행·검증을 연결한 하나의 그래프입니다.

## 폴더와 코드 위치

| 폴더 | 구현 내용 |
| --- | --- |
| [agent](agent/README.md) | `unlockops`: 그래프, 의도 해석, MCP 클라이언트, 상태 모델, 정책 판정, 공통 설정 |
| [rag](rag/README.md) | `unlockops_rag`: 문서 청킹, TF-IDF/선택적 임베딩 검색, 원문 조항 조회 |
| [mcp](mcp/README.md) | `unlockops_mcp`: Policy/Business MCP, 토큰 인증, Spring 내부 API HTTP 어댑터 |
| [worker](worker/README.md) | `unlockops_worker`: RabbitMQ 소비·결과 발행, 체크포인트 재개 |
| [backend](backend/README.md) | Java 21 / Spring Boot 3.5.7 / Maven, 인증·승인·업무 DB·outbox/inbox |
| [frontend](frontend/README.md) | Vue 3 / Vite / TypeScript, 접수·본인 조회·승인 카드·내 승인 현황 |
| [data](data/README.md) | 정책 원문, 회사 접근 권한표; 생성 체크포인트는 Git 제외 |
| [infra](infra/README.md) | 공통 Python Dockerfile, 로컬 디버깅용 Compose override |
| [docs](docs/README.md) | 아키텍처, 상태·메시지 계약, 실행·검증 안내 |
| [tests](tests/README.md) | 실행 중인 전체 스택을 대상으로 하는 선택적 통합 테스트 |

Python 의존성은 루트 `pyproject.toml`과 `uv.lock`으로 함께 관리합니다.
폴더 이름 `mcp/`와 SDK 패키지 `mcp`가 충돌하지 않도록 실제 프로젝트 패키지는 `unlockops_mcp`입니다.

## 전체 서비스 실행

Docker Desktop을 실행한 뒤 루트에서 실행합니다.

```sh
cp .env.example .env
docker compose up --build
```

화면: <http://localhost:8088>, RabbitMQ 관리: <http://localhost:15672>.
데모 비밀번호는 `.env`의 `DEMO_PASSWORD`입니다.
`kim_dev`는 신청자, `park_lead`는 결제 TF 승인자, `yoon_head`는 개발팀 부서장,
`song_ops`는 전체 이력 조회 담당자입니다. `song_ops`가 지정 승인자를 대신할 수는 없습니다.

중단은 `docker compose stop`입니다. DB·체크포인트 볼륨은 유지됩니다.

## 로컬 개발과 에이전트 디버깅

Python 3.11, uv, Node 22.12 이상, Java 21, Maven을 사용합니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest -q
```

가상환경 설치 후 아래 세 명령을 각각 별도 터미널에서 실행합니다.
DB·RabbitMQ·backend 준비와 VS Code F5 순서는 [디버깅 안내](docs/debugging.md)를 참고하세요.

```sh
.venv/bin/python -m unlockops_mcp.policy
.venv/bin/python -m unlockops_mcp.business
.venv/bin/python -m unlockops_worker
```

Policy MCP는 8001, Business MCP는 8002를 사용합니다.
VS Code에서는 `.venv` 인터프리터를 선택하고 제공된 디버그 구성을 실행합니다.
Windows에서는 `.venv/bin/python` 대신 `.venv/Scripts/python.exe`를 사용합니다.

## 설정과 책임 경계

Python은 루트 `.env`를 로드하되 프로세스에 이미 설정된 환경변수를 우선합니다.
상대 데이터·체크포인트 경로는 프로젝트 루트 기준이며, Compose는 컨테이너 전용 주소를 전달합니다.
Spring을 직접 실행할 때는 VS Code의 `envFile` 또는 환경변수 전달이 필요합니다.
API 키가 필요한 모드는 사용자가 명시적으로 활성화해야 하며 demo 모드는 외부 모델을 호출하지 않습니다.

Business MCP는 `BACKEND_INTERNAL_URL`의 Spring `/internal/**` API를 호출하며 DB에 직접 연결하지 않습니다.
Spring이 승인·요청 상태뿐 아니라 모의 SaaS 조회·권한 변경·예산·실행 영수증을 관리하고 실행 직전 자격을 재검증합니다.
`MCP_TOKEN`은 Agent→MCP 인증, `INTERNAL_API_TOKEN`은 MCP→Spring 인증입니다.
로컬 Spring과 Business MCP에 같은 INTERNAL_API_TOKEN을 전달하며 Compose는 이를 함께 설정합니다.
회사 권한 규정 검색·원문 조회는 Business MCP에 유지하고 상한·실행 판정은 Spring API에서 받습니다.

실행 결과는 [검증 안내](docs/verification.md), 공통 계약은 [계약 문서](docs/contracts/README.md)를 참고하세요.
협업 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)와 [Git 컨벤션](docs/git-convention.md)을 따릅니다.
