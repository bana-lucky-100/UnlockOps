# Worker

C2 담당입니다. 진입점은 `unlockops_worker/__main__.py`입니다.

- RabbitMQ analysis/execution 및 v2.analysis/v2.execution 큐를 소비하고 결과·진행 이벤트를 results 큐에 발행합니다.
- v1은 요청 ID, v2는 작업 종류·업무 ID·명령·event_id를 LangGraph thread_id로 사용하여 SQLite 체크포인트를 재개합니다.
- 결과 발행 확인 후 작업을 ACK합니다. 동일 승인 작업의 중복 변경은 MCP의 실행 영수증으로 방지합니다.
- 현재 SQLite 구성은 worker 한 개만 실행합니다.
- 원본 동작대로 backend HTTP API가 아닌 큐 메시지로 업무 결과를 전달합니다.

루트 가상환경 설치, DB·RabbitMQ·backend·두 MCP 시작 후 실행합니다.

```sh
.venv/bin/python -m unlockops_worker
```

환경변수와 로컬 시작 순서는 [디버깅 안내](../docs/debugging.md)를 참고하세요.

## Phase 2 연결

`phase2.py`가 큐/버전/명령을 검증하고 승인 분석·승인 실행·회수 점검 그래프로 분기합니다.
실행 그래프는 서버 승인 계획을 새로 조회하므로 분석 체크포인트가 없어도 실행할 수 있습니다.
v2 완료 결과는 발행 전에 저장합니다. 발행 실패 후 재전달하면 같은 결과·event_id만 재발행하고 도구를 반복 실행하지 않습니다.
회수는 전체 페이지와 스냅샷을 검증하고 후보 결과를 전달하며 최종 저장·알림·DONE은 Spring이 결정합니다.
도구는 작업당 기본 30회, 회수는 기본 500행/2,000,000바이트로 제한합니다. 전체 스택 검증 상태는 [구현 기록](../IMPLEMENTATION.md)을 참고하세요.
