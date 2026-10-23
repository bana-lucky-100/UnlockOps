# 환경변수

설정 예제는 루트 [`.env.example`](../.env.example)이다. 이 문서는 저장소에서 명시적으로 읽거나 안내하는 변수와 적용 경로를 정리한다. 프레임워크·OS가 지원하는 모든 환경변수를 나열하지는 않는다.

## 로딩과 적용 범위

| 실행 경로 | 설정 전달 |
|---|---|
| 로컬 Python Agent/Worker/MCP | `common/settings.py`가 루트 `.env`를 읽는다. 이미 설정된 프로세스 환경변수가 우선한다. |
| 로컬 Spring | 루트 `.env`를 자동으로 읽지 않는다. 프로세스 환경변수 또는 VS Code Spring 실행 구성의 `envFile`로 전달한다. |
| Docker Compose | 루트 `.env`는 보간 입력이다. `compose.yaml`의 `environment`에 명시된 값만 컨테이너로 전달한다. |
| Vite | `frontend/.env.local`에 프론트 설정을 둔다. `VITE_*`는 빌드 결과에 공개되며 변경 후 재시작/재빌드한다. |
| 테스트·평가 | 선택 검사는 프로세스 환경으로 활성화한다. 격리 평가용 값은 실행기가 관리한다. |

기존 `.env`는 예제 수정으로 자동 갱신되지 않는다. 필요한 항목을 직접 옮긴 뒤 해당 서비스를 재시작한다. Compose 설정 변경은 컨테이너 재생성에 반영한다.

## Backend·데이터베이스·브로커

표의 기본값은 별도 설정이 없는 코드 기준이다. 예제와 Compose는 로컬 시연을 위해 일부 값을 명시한다.

| 변수 | 기본값·우선순위 | Compose 적용 |
|---|---|---|
| `POSTGRES_DB` | `unlockops`; Spring DB URL의 기본 DB명 | PostgreSQL과 backend DB URL에 사용 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | `unlockops`, `unlockops-local-only` | PostgreSQL/backend 연결 계정 |
| `DB_URL` | `jdbc:postgresql://localhost:5432/${POSTGRES_DB}` | 컨테이너 호스트 `postgres`로 고정 |
| `DB_USER`, `DB_PASSWORD` | 각각 `POSTGRES_USER`, `POSTGRES_PASSWORD`보다 우선 | 공유 `POSTGRES_*`에서 설정 |
| `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | `unlockops`, `unlockops-local-only` | 브로커/backend/Worker 연결 계정 |
| `RABBIT_HOST` | backend/Worker 모두 `localhost` | `rabbitmq`로 고정 |
| `RABBIT_USER`, `RABBIT_PASSWORD` | 각각 `RABBITMQ_USER`, `RABBITMQ_PASSWORD`보다 우선 | 공유 `RABBITMQ_*`에서 설정 |
| `DEMO_ENABLED` | Spring 기본 `false`; 예제는 `true` | `true`로 고정 |
| `DEMO_PASSWORD` | Spring 기본 빈 값; 시연 활성화 시 8자 이상 필요 | 예제·Compose 기본 `demo1234` |
| `DEMO_SEED_PATH` | 기본 빈 값; 시연 활성화 시 seed와 누락 정책 revision 2·3 준비 | `/app/data/phase2/seed.sql`로 고정 |
| `RECLAIM_SCHEDULE_ENABLED` | `false`; `reclaim_scopes.enabled`도 켜져야 동작 | 루트 환경에서 보간하여 전달 |
| `RECLAIM_CRON` | `0 0 9 * * *`; Spring 6필드, 시간대 `Asia/Seoul` 고정 | 루트 환경에서 보간하여 전달 |
| `INTERNAL_API_TOKEN` | `replace-this-local-internal-api-token`; MCP와 Spring이 같아야 함 | backend와 두 MCP에 전달 |

호환 별칭은 **독립 실행 Spring**에서만 사용할 수 있다. 정식 변수가 설정되어 있으면 빈 문자열·`false`도 정식 값이 우선하므로 두 이름을 동시에 설정하지 않는다.

| 정식 이름 | 이전 별칭 |
|---|---|
| `DEMO_SEED_PATH` | `DEMO_PHASE2_SEED_PATH` |
| `RECLAIM_SCHEDULE_ENABLED` | `PHASE2_RECLAIM_SCHEDULE_ENABLED` |
| `RECLAIM_CRON` | `PHASE2_RECLAIM_CRON` |

Compose는 이전 별칭을 전달하지 않는다. 기존 `.env`의 `PHASE2_RECLAIM_*`는 `RECLAIM_*`로 옮긴다. 새 예제의 `RECLAIM_SCHEDULE_ENABLED=false`를 그대로 둔 채 이전 별칭만 `true`로 바꾸면 Spring에서도 정식 값이 우선한다.

Spring Boot 표준 재정의도 지원한다. `SERVER_PORT`는 기본 8080이다. `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`, `SPRING_RABBITMQ_HOST/PORT/USERNAME/PASSWORD`는 YAML의 해당 속성보다 우선한다. 루트 `.env`에 작성한 표준 재정의는 현재 Compose에 전달되지 않는다. `RABBIT_PORT`는 Worker 전용이며 Spring 포트 변경에는 `SPRING_RABBITMQ_PORT`를 쓴다.

## Python Worker·MCP·모델

| 변수 | 코드 기본값·용도 | Compose 적용 |
|---|---|---|
| `AGENT_MODE` | `demo`; `llm`은 모델을 사용하는 요청 해석·안내·보고서 경로 | Worker에 전달 |
| `RABBIT_URL`, `RABBITMQ_URL` | 비어 있음. 비어 있지 않은 `RABBIT_URL` → `RABBITMQ_URL` → 개별 연결 설정 순 | 전달하지 않음 |
| `RABBIT_PORT` | Worker 기본 `5672`; URL 사용 시 개별 연결 설정 무시 | 전달하지 않음, 기본 5672 |
| `POLICY_MCP_URL` | `http://localhost:8001/mcp` | `http://policy-mcp:8000/mcp` 고정 |
| `BUSINESS_MCP_URL` | `http://localhost:8002/mcp` | `http://business-mcp:8000/mcp` 고정 |
| `BACKEND_INTERNAL_URL` | `http://localhost:8080`; MCP → Spring | `http://backend:8080` 고정 |
| `MCP_TOKEN` | `replace-this-local-mcp-token`; Worker → MCP | Worker와 두 MCP에 전달 |
| `MCP_HOST` | 로컬 두 MCP 모두 `127.0.0.1` | 이미지에서 `0.0.0.0` 고정 |
| `MCP_PORT` | 로컬 Policy `8001`, Business `8002` | 이미지에서 `8000` 고정 |
| `CHECKPOINT_PATH` | `data/checkpoints/checkpoints.sqlite` | Worker `/state/checkpoints.sqlite` 고정 |
| `DATA_DIR` | `data`; Settings 필드로 남지만 현재 업무 경로에서 소비하지 않음 | 이미지 `/app/data` |
| `LLM_API_KEY`, `LLM_MODEL` | 기본 미설정; `llm` 모드에서 둘 다 필요 | Worker에 전달 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Worker에 전달 |
| `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` | 기본 빈 값. `DocumentIndex` 유틸 전용; URL·모델을 모두 설정하면 임베딩 사용 | 두 MCP에 전달 |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | LangChain/LangSmith 라이브러리 설정. 예제는 추적 `false`, 키 빈 값, 프로젝트 `unlockops-local` | 전달하지 않음 |

현재 회사·revision에 고정한 정책 검색은 로컬 TF-IDF다. `EMBEDDING_*`를 설정해도 현재 검색 경로를 임베딩으로 전환하지 않는다. Python 상대 경로는 저장소 루트 기준이다.

두 MCP를 로컬에서 실행할 때 공통 `.env`에 활성 `MCP_PORT`를 넣으면 포트가 충돌한다. 프로세스별로 지정한다. VS Code 실행 구성도 서버별 포트를 지정한다.

```sh
MCP_HOST=127.0.0.1 MCP_PORT=8001 .venv/bin/python -m unlockops_mcp.policy
MCP_HOST=127.0.0.1 MCP_PORT=8002 .venv/bin/python -m unlockops_mcp.business
```

## 프론트·검증·자동화

| 변수 | 용도·관리 위치 |
|---|---|
| `VITE_UO_MOCK` | `frontend/.env.local`에서 `true`일 때 일부 비용·회수 화면의 모의 데이터 사용. 기본 비활성. 루트 `.env`는 Vite에 적용되지 않음. |
| `BASE_URL` | Vite가 제공하는 자산 기준 경로. 환경변수 예제에 직접 할당하지 않음. |
| `RUN_LIVE_STACK`, `LIVE_BASE_URL` | 선택 live 검사. `RUN_LIVE_STACK=1`일 때 실제 요청·승인 생성; 기본 건너뜀. URL 기본 `http://localhost:8088`. 새 전용 시연 스택에서 실행. |
| `PHASE2_EVAL_INPUT` | `scripts/evaluate_phase2.py`가 격리 평가 bundle 절대 경로를 주입. 사용자 `.env`에 설정하지 않음. |
| `EVAL_PASSWORD` | 격리 평가 Compose가 evaluator에 전달하는 합성 계정 비밀번호. 사용자 `.env`에 설정하지 않음. |
| `GITHUB_STEP_SUMMARY` | GitHub Actions가 제공하는 결과 파일 경로. |
| `EVAL_SUITE` | 평가 workflow의 수동 실행 입력(`smoke`/`full`)을 실행 명령에 전달. |
| `PR_BASE_SHA`, `PUSH_BEFORE_SHA` | CI workflow가 이벤트의 SHA로 설정하는 변경 검사 입력. |
| `RUN_TESTS` | `frontend/Dockerfile`의 build ARG. 격리 평가가 `true`로 전달. 런타임 환경변수 아님. |
| `PYTHONUNBUFFERED` | Python 이미지에서 `1`로 설정하는 표준 출력 옵션. |
| `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS` | RabbitMQ 컨테이너 입력. Compose가 공유 `RABBITMQ_USER/PASSWORD`를 매핑. |

예: `RUN_LIVE_STACK=1 LIVE_BASE_URL=http://localhost:8088 .venv/bin/python -m pytest tests/test_live_stack.py -v`.

## 2026-10-23 전수 조사 결과

Python AST의 환경 접근과 `project_path`, Spring YAML placeholder·Java 설정 주입, Compose placeholder·컨테이너 environment, Dockerfile ENV/ARG, Vite 환경 참조, VS Code·CI·평가·선택 테스트 및 README를 대조했다.

- 직접 참조 이름 45개 중 자동화/내장 변수 4개(`BASE_URL`, `EVAL_PASSWORD`, `PHASE2_EVAL_INPUT`, `GITHUB_STEP_SUMMARY`)를 제외한 **41개 모두** 예제에 활성 또는 주석 할당으로 안내한다.
- 기존 예제에 할당 예시가 없던 **16개**를 추가했다: `RECLAIM_SCHEDULE_ENABLED`, `RECLAIM_CRON`, `DEMO_SEED_PATH`, `DB_URL`, `DB_USER`, `DB_PASSWORD`, `RABBIT_HOST`, `RABBIT_PORT`, `RABBIT_USER`, `RABBIT_PASSWORD`, `RABBITMQ_URL`, `MCP_HOST`, `MCP_PORT`, `VITE_UO_MOCK`, `RUN_LIVE_STACK`, `LIVE_BASE_URL`. 이 중 MCP host/port는 기존에 이름 설명만 있었다.
- 소비 코드가 없는 `ACCESS_MATRIX_PATH`, `LOG_LEVEL`을 예제에서 제거했다. 루트 `TZ`도 Compose에 전달되지 않고 회수 스케줄은 시간대를 코드에서 고정하므로 제거했다. `DATA_DIR`과 `EMBEDDING_*`는 남아 있는 설정/유틸의 현재 한계를 명시했다.
- 이전 Spring 별칭은 주석 예시로 남겼다. 제품 로직·Compose 전달 정책·HTTP/메시지 계약은 변경하지 않는다.

확인할 원본: [Spring 설정](../backend/src/main/resources/application.yml), [Compose](../compose.yaml), [Python 설정](../agent/unlockops/common/settings.py), [Worker 연결](../worker/unlockops_worker/__main__.py), [MCP 실행](../mcp/README.md), [RAG 유틸](../rag/README.md), [선택 테스트](../tests/README.md).

예제의 Compose 보간 결과는 서비스를 시작하지 않고 확인할 수 있다. 실제 `.env` 대신 예제 파일을 지정한다.

```sh
docker compose --env-file .env.example config --quiet
RECLAIM_SCHEDULE_ENABLED=true RECLAIM_CRON='0 30 10 * * MON-FRI' docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example -f compose.yaml -f infra/compose.debug.yaml config --quiet
```
