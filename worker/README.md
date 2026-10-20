# Worker

C2 담당입니다. 진입점은 `unlockops_worker/__main__.py`입니다.

- RabbitMQ analysis/execution 큐를 소비하고 결과·진행 이벤트를 results 큐에 발행합니다.
- 요청 ID를 LangGraph thread_id로 사용하여 SQLite 체크포인트를 재개합니다.
- 결과 발행 확인 후 작업을 ACK합니다. 동일 승인 작업의 중복 변경은 MCP의 실행 영수증으로 방지합니다.
- 현재 SQLite 구성은 worker 한 개만 실행합니다.
- 원본 동작대로 backend HTTP API가 아닌 큐 메시지로 업무 결과를 전달합니다.

루트 가상환경 설치, DB·RabbitMQ·backend·두 MCP 시작 후 실행합니다.

```sh
.venv/bin/python -m unlockops_worker
```

환경변수와 로컬 시작 순서는 [디버깅 안내](../docs/debugging.md)를 참고하세요.
