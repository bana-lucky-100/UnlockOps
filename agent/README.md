# Agent

B팀 담당입니다. 원본 `python/unlockops`에서 에이전트 코드를 옮겼습니다.
현재는 하나의 LangGraph에 진단·승인·실행 흐름이 연결되어 있으며 두 독립 Agent로 분리되어 있지는 않습니다.

## 실습 코드처럼 읽는 순서

1. `graph.py`의 `AgentState`: 노드들이 공유하는 작업 기록입니다. `total=False`이므로 처음부터 모든 필드가 필요하지 않습니다.
2. `planner.py`의 `model()`: LLM 연결 설정입니다. `@lru_cache(maxsize=1)`로 연결 객체만 재사용하며 답변은 캐시하지 않습니다. 데모 모드에서는 외부 모델을 호출하지 않습니다.
3. `graph.py`의 `interpret_node` 등: 각 함수는 State를 읽고 변경할 필드만 dict로 반환합니다.
4. `route_after_scope`, `route_after_judge`, `route_after_execute`, `route_after_verify`: 다음 노드 이름을 반환하는 분기 함수입니다.
5. `build_graph()`: 실습처럼 `add_node`, `add_edge`, `add_conditional_edges`, `compile` 순서로 연결을 확인합니다.

MCP를 호출하는 노드는 `partial(context_node, tools=tools)`처럼 공통 연결을 미리 넣습니다.
`partial`은 함수 인자 일부를 고정하는 Python 기능이며, 도구 객체를 State·체크포인트에 저장하지 않기 위한 구성입니다.
노드 이름과 State 필드 이름을 유지하여 기존 승인 대기·재개 흐름을 이어갑니다.
LLM 환경변수 변경은 worker 재시작 후 반영합니다.

실습의 LangChain `@tool`은 모델에 제공할 로컬 도구를 만들고, 이 프로젝트의 MCP 서버는
`@mcp.tool(...)`로 원격 호출 가능한 도구를 등록합니다. 임의의 노드 데코레이터 대신 StateGraph의
명시적 노드 등록을 사용합니다. `create_agent`용 `@before_agent` 미들웨어와는 API가 다르므로,
요청 범위 검사는 현재의 `scope` 노드에서 수행합니다.

| 파일 | 수정할 내용 |
| --- | --- |
| `unlockops/graph.py` | AgentState, 노드, 분기, 승인 interrupt, 실행·검증 재시도 |
| `unlockops/planner.py` | 규칙 기반 의도 추출, LLM 프롬프트·읽기 도구 선택 |
| `unlockops/answering.py` | 검색 문서를 활용한 안내 생성, 인용 원문 검사, LLM 내용 검토 |
| `unlockops/response_context.py` | 조회 사실·확정 판정·회사 규정·작성 기준을 답변 입력으로 정리 |
| `unlockops/tools.py` | 두 MCP 클라이언트, timeout, 사용자·자원·플랫폼 범위 제한 |
| `unlockops/models.py` | Platform, Status, Job, Plan, Result |
| `unlockops/contracts.py` | MCP 도구별 입력·응답 모델, 공통 오류 정규화; 두 서버와 공유 |
| `unlockops/rules.py` | 직무·직급·소속·좌석·예산에 따른 명시적 판정; MCP도 재사용 |
| `unlockops/settings.py` | 루트 .env 로딩, 데이터·체크포인트 경로, MCP 주소 |
| `tests/` | 시나리오, 승인 전 변경 차단, 체크포인트 재개, 패키지 이식 검증 |

작업 흐름은 `interpret → scope → context → gather → judge → prepare_response` 후 처리 경로로 나뉩니다.
의도 추출 결과 `out_of_scope=true`는 scope에서 `MANUAL_REVIEW / REQUEST_OUT_OF_SCOPE`로 종료합니다.
다른 플랫폼 이름의 단순 언급으로 차단하지 않으며, 범위 검사를 통과해도 별도의 정책·승인 검증을 거칩니다.
judge에서 답변·승인·거절·수동 검토를 결정합니다. 거절·수동 검토는 종료하고 승인 대기는 체크포인트에 저장합니다.
사용법 문의와 필요한 권한을 이미 보유한 요청은 `answer → END`로 연결합니다.
RabbitMQ 진입점은 `worker/unlockops_worker/__main__.py`입니다.

`prepare_response`는 외부 조회·모델 호출 없이 State의 값을 정리해 `response_context`에 저장합니다.
입력에는 질문·플랫폼, 현재 권한·직무·직급·허용 상한, 자원별 TF·부서·예산 조건,
코드가 확정한 처리 경로·상태·사유·요청 역할, 문서 근거와 작성 기준이 들어갑니다.
직원·승인자 ID와 이름·로그인 정보·실행 키를 포함하지 않으며, 좌석 예산은 금액 대신 충족 여부만 전달합니다.
미조회 값은 null로 남기고 `current_permissions_checked`로 미조회와 조회 결과 권한 없음(role=null)을 구분합니다.
회사 권한 문서 3·4·7절의 관련 청크를 각 1개, 선택 플랫폼 검색 결과를 최대 5개 전달하며
출처·조항·버전·원문 해시를 보존합니다. 현재 작성 가이드는 코드의 고정 기준이며 별도 문서 연결은 하지 않았습니다.
승인·거절·수동 검토 경로의 입력도 준비하지만, 이번 단계에서 LLM 작성은 기존 answer 경로에만 연결합니다.
기존 체크포인트에 response_context나 명시적 상한이 없으면 저장된 조회 사실로 입력을 구성합니다.

`interpret`는 `Intent.request_type`에 사용자가 원하는 도움을 기록합니다.

| 값 | 의미 | 예시 |
| --- | --- | --- |
| `GUIDE` | 사용법 문의 | push 방법, 권한 신청 절차 안내 |
| `TROUBLESHOOT` | 오류 해결 | push 실패, 권한이 있는데 403 발생 |
| `ACCESS_REQUEST` | 권한 신청 | Write 부여, 채널 초대, Copilot 좌석 신청 |

데모는 최소 규칙으로 분류하고 LLM 모드는 문맥에 따라 구조화된 값을 반환합니다.
이 값은 State와 interpret 진행 이벤트에 저장하며 실제 권한 부족·부여 자격은 MCP 조회와 정책 판정으로
확인합니다. 기존 Intent 데이터에 값이 없으면 `TROUBLESHOOT`로 읽습니다.
`GUIDE`는 자원 이름 없이도 문서 안내가 가능하며 권한 부여 계획을 만들지 않습니다.
`TROUBLESHOOT`와 `ACCESS_REQUEST`는 조회 결과에 따라 승인·거절·수동 검토로 분기하고,
필요 권한을 이미 보유한 경우에는 답변으로 보냅니다. 기존 좌석의 명시적 중복 신청은 거절합니다.

답변은 준비된 response_context의 실제 검색 결과·회사 규정·조회 사실·판정을 사용합니다.
추가 조사에서 읽은 문서는 최종 evidence에도 보존합니다.
데모는 문서 원문을 발췌하고, LLM 모드는 준비한 입력으로 안내를 생성한 뒤 별도 모델 호출로
각 주장과 질문의 관련성을 검토합니다. 단계마다 인용 ID와 원문 발췌의 일치를 코드로 검사합니다.
선택 플랫폼의 검색 근거가 없거나 검토를 통과하지 못하면 `MANUAL_REVIEW`로 종료합니다.
모델 호출 장애는 worker의 기술 실패 처리로 전달합니다.

안내는 기존 서버 계약의 `MANUAL_REVIEW / RAG_GUIDANCE`로 전달하며 plan과 verification_ok는 null입니다.
proposal에 답변과 출처를 담고, 내부 handling은 ANSWER로 기록합니다.
화면 상태와 공개 이력은 기존 담당자 검토 표시로 남습니다. 안내 완료 전용 상태는 서버 담당자와
계약을 합의한 뒤 별도로 도입할 수 있습니다. 백엔드·DB·프론트 변경 없이 기존 proposal 표시를 사용합니다.
권한 반영 완료인 `DONE`의 verification_ok=true 검사와 실행 영수증 검사는 유지합니다.

gather는 필수 사실·규정을 먼저 조회한 뒤 LLM 선택 조회를 실행합니다. 실제 읽기 호출 한도는
분석당 30회(context 포함), 선택 조회 시도는 캐시·범위 오류를 포함해 최대 10회입니다.
동일 선택 조회는 gather 내 성공 결과를 재사용하며 승인 후 실행·검증에는 캐시를 사용하지 않습니다.
선택 조회 한도 소진은 필수 조회 결과를 바탕으로 판정을 계속하고, 필수 조회 실패는 승인으로 진행하지 않습니다.
검증은 `verified=false` 또는 재시도 가능한 오류만 최대 3회 확인합니다. 영구 오류·응답 형식 오류는 즉시
실패하며 검증 실패 때문에 권한 부여를 다시 실행하지 않습니다. [MCP 계약](../docs/contracts/mcp.md)을 참고하세요.

루트에서 설치·테스트합니다. 서비스별 별도 가상환경은 만들지 않습니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest agent/tests -q
```

VS Code의 `UnlockOps: Python current test`로 테스트 파일에 중단점을 걸 수 있습니다.
실제 worker 디버깅은 [공통 안내](../docs/debugging.md)를 참고하세요.
