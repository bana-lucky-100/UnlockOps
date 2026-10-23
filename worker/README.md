# Worker

진입점은 `unlockops_worker/__main__.py`, 공통 작업 실행기는 `runtime.py`입니다.

| 큐 | 처리 |
|---|---|
| `unlockops.v2.analysis` | ACCESS_REQUEST/ANALYZE → 승인 분석, RECLAIM_SCAN/RECLAIM_CHECK → 회수 점검 |
| `unlockops.v2.execution` | ACCESS_REQUEST/EXECUTE → 승인 후 실행·검증 |
| `unlockops.results` | 서버가 소비하는 진행·결과 이벤트 |
| `unlockops.dead` | 잘못된 작업과 재시도 불가능한 메시지 |

schema_version=2의 작업만 받습니다. 큐 이름은 기존 배포·계약과의 호환을 위해 유지하며 별도의 구 실행기는 없습니다.
분석·실행·회수별 LangGraph 체크포인트를 작업 event_id에 연결합니다. 동일 작업 ID에 다른 입력을 재사용하면 거부합니다.
완료 이벤트를 먼저 저장하고 발행 확인 뒤 ACK합니다. 결과 발행 실패 후 재전달은 저장된 이벤트를 재발행하며 도구를 반복 실행하지 않습니다.
SQLite 구성은 Worker 한 개, single-flight 처리를 유지합니다. 도구는 작업당 기본 30회, 회수 결과는 500행/2,000,000바이트로 제한합니다.

```sh
.venv/bin/python -m unlockops_worker
```

서버·RabbitMQ·두 MCP가 먼저 실행돼 있어야 합니다. 환경변수는 [디버깅 안내](../docs/debugging.md)를 참고하세요.
구 `analysis`/`execution` 큐는 더 이상 소비하지 않습니다. 과거 메시지·체크포인트는 삭제하지 않으며 구 승인 대기 건은 최신 조건으로 재접수해야 합니다.
