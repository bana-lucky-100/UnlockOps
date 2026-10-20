# Agent

B팀 담당입니다. 원본 `python/unlockops`에서 에이전트 코드를 옮겼습니다.
현재는 하나의 LangGraph에 진단·승인·실행 흐름이 연결되어 있으며 두 독립 Agent로 분리되어 있지는 않습니다.

| 파일 | 수정할 내용 |
| --- | --- |
| `unlockops/graph.py` | AgentState, 노드, 분기, 승인 interrupt, 실행·검증 재시도 |
| `unlockops/planner.py` | 규칙 기반 의도 추출, LLM 프롬프트·읽기 도구 선택 |
| `unlockops/tools.py` | 두 MCP 클라이언트, timeout, 사용자·자원·플랫폼 범위 제한 |
| `unlockops/models.py` | Platform, Status, Job, Plan, Result |
| `unlockops/rules.py` | 기존 회사 권한표의 상한·승인자 기준 조회, 실제 자격·RAG 근거 검사; MCP도 재사용 |
| `unlockops/permission_proposal.py` | LLM의 권한·이유·근거 ID 제안과 검증. 사용자 답변 생성과 분리 |
| `unlockops/settings.py` | 루트 .env 로딩, 데이터·체크포인트 경로, MCP 주소 |
| `tests/` | 시나리오, 승인 전 변경 차단, 체크포인트 재개, 패키지 이식 검증 |

작업 흐름은 `interpret → context → gather → judge → approval → execute → verify → finish`입니다.
거절·수동 검토·이미 보유는 judge에서 끝나고 승인 대기는 체크포인트에 저장합니다.
RabbitMQ 진입점은 `worker/unlockops_worker/__main__.py`입니다.

권한 판단 근거는 기존 `data/policy_corpus.md`와 `data/company-a-access-matrix.md`입니다.
`rules.py`의 `ceiling()`은 회사 권한표 3절의 플랫폼·자원·직무·직급에 해당하는 셀을 직접 읽습니다.
승인자 기준도 같은 문서의 7절에서 확인합니다. 표를 해석할 수 없으면 권한을 추측하지 않고 차단합니다.

`llm` 모드에서는 judge 안에서 RAG 근거와 실제 직원 정보를 읽어 권한 전용 제안을 받습니다.
실제 직원 정보와 RAG 청크를 입력하고 `decision`, `requested_role`, `reason`, `evidence_ids`를 반환받습니다.
인용 근거의 현재 원문 해시, 존재하지 않는 근거 ID, 요청 역할 변경을 확인합니다. 제안 후에는 원문 표의
상한과 실제 TF 소속·부서·예산·현재 권한을 검증합니다. 자격 미달은 모델이 뒤집을 수 없습니다.
제안 오류·모델 장애는 수동 검토로 보냅니다. `demo`는 모델을 호출하지 않고 원문 표와 실제 사실로 처리합니다.

권한 제안과 원문 해시는 체크포인트와 judge 이벤트에 남깁니다. 기존 답변 생성 프롬프트와
결과 큐·실행 계획의 필드 구성은 변경하지 않았습니다. 모델 제안은 실제 사람 승인을 대신하지 않습니다.

루트에서 설치·테스트합니다. 서비스별 별도 가상환경은 만들지 않습니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest agent/tests -q
```

VS Code의 `UnlockOps: Python current test`로 테스트 파일에 중단점을 걸 수 있습니다.
실제 worker 디버깅은 [공통 안내](../docs/debugging.md)를 참고하세요.
