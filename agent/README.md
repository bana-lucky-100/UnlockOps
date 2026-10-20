# Agent

B팀 담당입니다. 원본 `python/unlockops`에서 에이전트 코드를 옮겼습니다.
현재는 하나의 LangGraph에 진단·승인·실행 흐름이 연결되어 있으며 두 독립 Agent로 분리되어 있지는 않습니다.

| 파일 | 수정할 내용 |
| --- | --- |
| `unlockops/graph.py` | AgentState, 노드, 분기, 승인 interrupt, 실행·검증 재시도 |
| `unlockops/planner.py` | 규칙 기반 의도 추출, LLM 프롬프트·읽기 도구 선택 |
| `unlockops/tools.py` | 두 MCP 클라이언트, timeout, 사용자·자원·플랫폼 범위 제한 |
| `unlockops/models.py` | Platform, Status, Job, Plan, Result |
| `unlockops/rules.py` | 직무·직급·소속·좌석·예산에 따른 명시적 판정; MCP도 재사용 |
| `unlockops/settings.py` | 루트 .env 로딩, 데이터·체크포인트 경로, MCP 주소 |
| `tests/` | 시나리오, 승인 전 변경 차단, 체크포인트 재개, 패키지 이식 검증 |

작업 흐름은 `interpret → context → gather → judge → approval → execute → verify → finish`입니다.
거절·수동 검토·이미 보유는 judge에서 끝나고 승인 대기는 체크포인트에 저장합니다.
RabbitMQ 진입점은 `worker/unlockops_worker/__main__.py`입니다.

루트에서 설치·테스트합니다. 서비스별 별도 가상환경은 만들지 않습니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest agent/tests -q
```

VS Code의 `UnlockOps: Python current test`로 테스트 파일에 중단점을 걸 수 있습니다.
실제 worker 디버깅은 [공통 안내](../docs/debugging.md)를 참고하세요.
