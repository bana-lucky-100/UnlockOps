# Agent

B팀 담당입니다. 원본 `python/unlockops`에서 에이전트 코드를 옮겼습니다.
현재는 하나의 LangGraph에 진단·승인·실행 흐름이 연결되어 있으며 두 독립 Agent로 분리되어 있지는 않습니다.

## 폴더 구성

| 경로 | 역할 |
| --- | --- |
| `unlockops/access/` | 기존 안내·권한 판단·승인 대기·권한 부여·검증 흐름 |
| `unlockops/common/` | 작업·결과 모델, MCP 계약·클라이언트, 공통 설정 |
| `tests/` | 기존 흐름과 서비스 간 연동을 검증하는 테스트 |

worker는 `unlockops.access.graph`에서 그래프를 만들고, worker와 MCP 서버는
`unlockops.common`의 모델·계약·설정을 사용합니다. MCP의 권한 정책 검사는
기존처럼 `unlockops.access.rules`의 원문 해시 함수를 재사용합니다.
`reclaim`은 아직 구현하지 않아 폴더를 만들지 않았습니다.
이번 폴더 분리는 실행 프로세스나 승인 정책을 바꾸지 않으며, 그래프 노드 이름·체크포인트 상태·큐 메시지 계약을 유지합니다.

## 실습 코드처럼 읽는 순서

1. `unlockops/access/graph.py`의 `AgentState`: 노드들이 공유하는 작업 기록입니다. `total=False`이므로 처음부터 모든 필드가 필요하지 않습니다.
2. `unlockops/access/planner.py`의 `model()`: LLM 연결 설정입니다. `@lru_cache(maxsize=1)`로 연결 객체만 재사용하며 답변은 캐시하지 않습니다. 데모 모드에서는 외부 모델을 호출하지 않습니다.
3. `unlockops/access/graph.py`의 `interpret_node` 등: 각 함수는 State를 읽고 변경할 필드만 dict로 반환합니다.
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
| `unlockops/access/graph.py` | AgentState, 노드, 분기, 승인 interrupt, 실행·검증 재시도 |
| `unlockops/access/planner.py` | 규칙 기반 의도 추출, LLM 프롬프트·읽기 도구 선택 |
| `unlockops/access/answering.py` | 검색 문서를 활용한 안내 생성, 인용 원문 검사, LLM 내용 검토 |
| `unlockops/access/response_context.py` | 조회 사실·확정 판정·회사 규정·작성 기준을 답변 입력으로 정리 |
| `unlockops/common/tools.py` | 두 MCP 클라이언트, timeout, 사용자·자원·플랫폼 범위 제한 |
| `unlockops/common/models.py` | Platform, Status, Job, Plan, Result |
| `unlockops/common/contracts.py` | MCP 도구별 입력·응답 모델, 공통 오류 정규화; 두 서버와 공유 |
| `unlockops/access/rules.py` | 기존 회사 권한표의 상한·승인자 기준 조회, 실제 자격·RAG 근거 검사; MCP도 재사용 |
| `unlockops/access/permission_proposal.py` | LLM의 권한·이유·근거 ID 제안과 검증. 사용자 답변 생성과 분리 |
| `unlockops/common/settings.py` | 루트 .env 로딩, 데이터·체크포인트 경로, MCP 주소 |
| `tests/` | 시나리오, 승인 전 변경 차단, 체크포인트 재개, 패키지 이식 검증 |

작업 흐름은 `interpret → scope → context → gather → judge → prepare_response → compose_response` 후 처리 경로로 나뉩니다.
의도 추출 결과 `out_of_scope=true`는 scope에서 `MANUAL_REVIEW / REQUEST_OUT_OF_SCOPE`로 종료합니다.
다른 플랫폼 이름의 단순 언급으로 차단하지 않으며, 범위 검사를 통과해도 별도의 정책·승인 검증을 거칩니다.
judge에서 답변·승인·거절·수동 검토를 결정하고 compose_response에서 설명을 작성합니다.
일반 안내·거절·수동 검토는 종료하고 승인 대기는 체크포인트에 저장합니다.
RabbitMQ 진입점은 `worker/unlockops_worker/__main__.py`입니다.

`prepare_response`는 외부 조회·모델 호출 없이 State의 값을 정리해 `response_context`에 저장합니다.
입력에는 질문·플랫폼, 현재 권한·직무·직급·허용 상한, 자원별 TF·부서·예산 조건,
코드가 확정한 처리 경로·상태·사유·요청 역할, 문서 근거와 작성 기준이 들어갑니다.
직원·승인자 ID와 이름·로그인 정보·실행 키를 포함하지 않으며, 좌석 예산은 금액 대신 충족 여부만 전달합니다.
미조회 값은 null로 남기고 `current_permissions_checked`로 미조회와 조회 결과 권한 없음(role=null)을 구분합니다.
회사 권한 문서 3·4·7절의 관련 청크를 각 1개, 선택 플랫폼 검색 결과를 최대 5개 전달하며
출처·조항·버전·원문 해시를 보존합니다. 현재 작성 가이드는 코드의 고정 기준이며 별도 문서 연결은 하지 않았습니다.
LLM 모드는 모든 판정 경로에서 같은 입력으로 생성·인용 검사·내용 검토를 수행합니다.
승인·거절·수동 검토는 검증된 proposal만 교체하며 상태·사유 코드·계획·계획 해시는 유지합니다.
생성 장애·근거 부족·검증 실패 시 기존 고정 안내를 보존합니다. 데모에서도 해당 경로는 고정 안내를 사용합니다.
일반 안내는 기존 answer_node 함수를 재사용하며, 생성 장애나 근거 검증 실패 시 수동 검토로 종료합니다.
이전 체크포인트의 answer 노드는 재개 호환을 위해 등록을 유지합니다.
승인 후 실행·검증 결과는 finish의 짧은 고정 문구로 안내하며, 담당자 알림은 연결하지 않습니다.
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
일반 안내의 모델 생성·검토 호출 장애는 answer_node에서 처리하여 `MANUAL_REVIEW / MODEL_UNAVAILABLE`로 종료합니다.

안내 성공은 `DONE / result_type=GUIDANCE / reasonCode=RAG_GUIDANCE`로 전달하며 plan과 verification_ok는 null입니다.
proposal에 답변과 출처를 담고, 내부 handling은 ANSWER로 기록합니다. 화면과 공개 이력 모두 안내 완료입니다.
권한 반영 완료는 `DONE / result_type=ACCESS_VERIFIED`이며 verification_ok=true가 필요합니다.
실행 작업의 DONE에는 서버의 실행 영수증 검사도 유지합니다. 안내 실패는 MANUAL_REVIEW이며 result_type은 null입니다.
이전 체크포인트의 안내 성공과 검증된 DONE은 Result 입력 경계에서 새 계약으로 정규화합니다.

gather는 필수 사실·규정을 먼저 조회한 뒤 LLM 선택 조회를 실행합니다. 실제 읽기 호출 한도는
분석당 30회(context 포함), 선택 조회 시도는 캐시·범위 오류를 포함해 최대 10회입니다.
동일 선택 조회는 gather 내 성공 결과를 재사용하며 승인 후 실행·검증에는 캐시를 사용하지 않습니다.
선택 조회 한도 소진은 필수 조회 결과를 바탕으로 판정을 계속하고, 필수 조회 실패는 승인으로 진행하지 않습니다.
검증은 `verified=false` 또는 재시도 가능한 오류만 최대 3회 확인합니다. 영구 오류·응답 형식 오류는 즉시
실패하며 검증 실패 때문에 권한 부여를 다시 실행하지 않습니다. [MCP 계약](../docs/contracts/mcp.md)을 참고하세요.

권한 판단 근거는 기존 `data/policy_corpus.md`와 `data/company-a-access-matrix.md`입니다.
`rules.py`의 `ceiling()`은 회사 권한표 3절의 플랫폼·자원·직무·직급에 해당하는 셀을 직접 읽습니다.
승인자 기준도 같은 문서의 7절에서 확인합니다. 표를 해석할 수 없으면 권한을 추측하지 않고 차단합니다.
규정 원문 읽기 실패(`POLICY_SOURCE_UNAVAILABLE`)와 권한표 해석 실패(`INVALID_ACCESS_MATRIX`)는
근거 수집·권한 판정 단계에서 `MANUAL_REVIEW`로 종료하며 승인 계획을 만들지 않습니다.
DB·통신·응답 계약 오류는 이 규정 오류 처리에 포함하지 않습니다.

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
