# 로컬 실행과 디버깅

모든 Python 명령은 UnlockOps 루트에서 실행합니다. Python 3.11, uv, Java 21, Maven,
Node 22.12 이상과 Docker Desktop이 필요합니다. 외부 모델 호출 없는 demo 모드가 기본입니다.

## 1. 설치

```sh
cp .env.example .env
uv --cache-dir .cache/uv sync --extra test
cd frontend
npm ci
```

VS Code에서 UnlockOps 루트를 열고 Python 인터프리터를 `.venv`로 선택합니다.
기존에 다른 인터프리터를 선택했다면 `Python: Select Interpreter`로 변경합니다.
권장 확장은 `.vscode/extensions.json`에 있습니다.

## 2. DB와 RabbitMQ

Docker Desktop 실행 후 루트에서 실행합니다.

```sh
docker compose -f compose.yaml -f infra/compose.debug.yaml up -d postgres rabbitmq
```

PostgreSQL은 localhost:5432, RabbitMQ는 localhost:5672입니다.
기존 전체 스택이 실행 중이면 동일 포트·worker를 중복 실행하지 않도록 먼저 정지하세요.
전체 스택과 로컬 worker를 함께 실행하면 같은 큐를 나눠 소비하여 중단점이 잡히지 않을 수 있습니다.

## 3. Backend

루트 .env에 `DEMO_ENABLED=true`와 `DEMO_PASSWORD`가 있는지 확인하고
VS Code에서 `UnlockOps: Spring Boot`를 F5로 실행합니다. Java 21을 선택합니다.
DB 연결 후 Flyway가 모의 회사 스키마와 데이터를 준비합니다. backend는 localhost:8080입니다.
터미널 Maven 실행 시에는 .env 값을 프로세스 환경변수로 별도 전달해야 합니다.

## 4. MCP 서버

`UnlockOps: MCP servers` 구성을 실행하면 두 서버가 8001과 8002에서 실행됩니다.
개별 구성을 사용하거나 루트의 서로 다른 터미널에서 실행할 수도 있습니다.

```sh
.venv/bin/python -m unlockops_mcp.policy
.venv/bin/python -m unlockops_mcp.business
```

Docker는 컨테이너 내부 8000, 호스트 Python은 서버별 8001/8002입니다.
로컬 .env에 `MCP_PORT=8000`을 공통으로 넣지 마세요.

## 5. Worker와 화면

MCP 두 서버가 준비되면 `UnlockOps: Agent worker`를 F5로 시작합니다.
프런트는 frontend에서 `npm run dev`로 시작한 뒤 localhost:5173에 접속합니다.
`kim_dev`로 요청하고, `park_lead`로 승인하여 실행 경로를 확인합니다.

중단점 위치:

- 의도 추출·LLM 프롬프트: `agent/unlockops/access/planner.py`
- 노드·판정·승인 대기·실행·검증: `agent/unlockops/access/graph.py`
- MCP→Spring HTTP 호출: `mcp/unlockops_mcp/backend_client.py`
- 실제 모의 권한 변경: `backend/src/main/java/com/unlockops/grant/service/GrantExecutionService.java`
- 메시지 소비·승인 재개: `worker/unlockops_worker/__main__.py`

승인 대기는 오류가 아니라 LangGraph interrupt입니다. 승인 후 같은 요청 ID의 체크포인트를 재개합니다.
CHECKPOINT_PATH를 바꾸거나 파일을 지우면 기존 승인 대기 작업을 재개할 수 없습니다.

## DB 없이 에이전트부터 디버깅

`agent/tests/test_scenarios.py`를 열고 `UnlockOps: Python current test`를 실행합니다.
가짜 MCP를 사용하는 그래프 테스트로 DB·RabbitMQ 없이 노드 중단점을 확인할 수 있습니다.
실제 MCP·큐 통합 검증과는 다릅니다.
