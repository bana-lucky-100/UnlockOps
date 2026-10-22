# MCP 도구 계약

공유 모델: `agent/unlockops/common/contracts.py`. 두 MCP 서버는 `ContractMCP` 경계에서 입력·출력을 검증하고
`tools/list`의 inputSchema/outputSchema에 같은 모델을 노출합니다. Agent 클라이언트도 같은 계약으로 검증합니다.
현재 설치된 `mcp` 1.x SDK를 사용하며 다른 FastMCP 패키지로 변경하지 않습니다.

## 입력과 성공 응답

입력에 정의되지 않은 필드는 거부합니다. employee_id/resource_id/problem_id는 UUID 문자열,
platform은 GITHUB/JIRA/SLACK/NOTION입니다. query/hint는 최대 5,000자,
search_policy.limit는 정수 1~10(기본 5), idempotency_key는 1~200자입니다.
read_policy는 POL-xx 또는 GH/JR/SL/NT-OFF-xx 형식, read_access_rule은 A-ACCESS-03/04/07만 허용합니다.
문서 존재 여부는 실제 인덱스에서 확인합니다.

| 도구 | 필수 입력 | 성공 응답 주요 필드 |
| --- | --- | --- |
| get_employee_profile | employee_id | id, employee_no, department_id/name, job_grade/family, head_id |
| resolve_resource | platform, hint | matches: 자원 목록, ambiguous: boolean |
| get_tf_membership | employee_id, resource_id | member: boolean, leader_id |
| get_current_permissions | employee_id, resource_id | role: string/null, can_browse: boolean(있는 경우) |
| check_budget | employee_id | budget: 예산/null |
| search_access_rules | query, employee_id, resource_id | hits: 근거 목록, maximum_role, context: 접근 조건 묶음 |
| read_access_rule | doc_id | chunks: 근거 목록 |
| search_policy | query, platform | hits: 근거 목록 |
| read_policy | doc_id | chunks: 근거 목록. article은 선택 입력 |
| grant_permission | problem_id, idempotency_key | ok:true, changed:boolean, role |
| verify_permission | employee_id, resource_id, requested_role | verified:boolean, ok/current(있는 경우) |

requested_role은 자동 처리 역할 Read/Write/Viewer/Developer/Can view/Can edit/Member/Seat 중 하나입니다.
이는 검증 도구 입력의 역할 목록이며 정책상 부여 가능 여부는 별도 판단합니다.
자원은 id/external_id/name/platform/access_scope가 필요하고, 부서·기밀 자원은 해당 부서 정보도 필요합니다.
matches 수와 ambiguous 값이 불일치하면 응답 형식 오류입니다.
예산 금액은 음수가 아닌 소수점 최대 두 자리 문자열이며 좌석 가격은 0보다 커야 합니다.
`search_access_rules.context`에는 같은 Spring 조회에서 받은 profile/resource_id/membership/current/budget/maximum_role이
필수로 포함됩니다. budget은 null일 수 있고, 최상위 maximum_role과 context.maximum_role은 같아야 합니다.
Agent는 이 묶음의 직원 ID·자원 ID를 확인하고 profile을 포함한 분석 사실을 한 번에 갱신합니다.
근거에는 chunk_id/doc_id/text/source/version이 필요합니다. 빈 chunks는 유효한 응답이지만,
필수 규정이 비어 있으면 Agent가 MISSING_SOURCE_EVIDENCE로 수동 검토 처리합니다.
정의된 핵심 필드를 엄격히 검사하고 source_hash/score/retrieval_mode 등 추가 메타데이터는 보존합니다.
문자열 `"false"`, 숫자 0/1을 JSON 불리언 대신 허용하지 않습니다.

## 오류

새 서버는 `CallToolResult.isError=true`로 반환하고 structuredContent와 JSON 텍스트에 다음을 담습니다.

```json
{"ok":false,"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Upstream service is temporarily unavailable","retryable":true}}
```

| 코드 또는 상황 | 재시도 |
| --- | --- |
| INVALID_TOOL_INPUT, UNKNOWN_TOOL, NOT_FOUND | 하지 않음 |
| INVALID_TOOL_OUTPUT, INTERNAL_TOOL_ERROR | 하지 않음 |
| APPROVAL_REQUIRED, PLAN_CHANGED 등 승인·사전조건 실패 | 하지 않음 |
| UPSTREAM_UNAVAILABLE, TOOL_TIMEOUT, 연결 장애 | 한도 내 재시도 |
| MCP_AUTH_FAILED, 잘못된 프로토콜 요청 | 하지 않음 |
| HTTP 408/429/502/503/504 | 한도 내 재시도 |
| 검증 성공 응답의 verified=false | 반영 지연으로 보고 한도 내 재조회 |

예외 메시지의 SQL·연결 문자열·외부 응답은 공통 메시지로 바꿉니다. 클라이언트는 isError만 보고 원래
오류 코드를 버리지 않고 code/retryable과 선택 reason을 보존해 ToolFailure로 바꿉니다. 형식이 잘못된 오류도
INVALID_TOOL_OUTPUT으로 처리합니다. 구형 비구조화 isError 응답은 일반 TOOL_ERROR로 종료합니다.

Business MCP는 Spring 내부 API를 호출하며 SQL 저장소는 제거했습니다. Spring의 구조화된 실행 오류에서
code/retryable/reason을 보존하고, 문서 오류는 POLICY_SOURCE_UNAVAILABLE로 통신 장애와 구분합니다.
401/403은 BACKEND_AUTH_FAILED로 재시도하지 않습니다. 일반 5xx·429·408은 UPSTREAM_UNAVAILABLE,
요청 시간 초과는 UPSTREAM_TIMEOUT으로 재시도 가능 처리합니다. 응답 원문·URL·토큰은 오류에 포함하지 않습니다.
기존 `{ok:false,error_code,retryable}` 형식도 이전 MCP와의 호환을 위해 계속 읽습니다.
성공 payload에 data/schema_version envelope를 추가하지 않습니다.
새 서버의 오류 형식을 이해하도록 Agent와 MCP를 함께 배포해야 합니다.

## 실행과 조회 한도

`Settings` 기본값: 실제 읽기 최대 30회, LLM 선택 조회 시도 최대 10회, 모델 반복 최대 4회,
권한 부여 최대 3회(최초 1회 + 재시도 2회), 실행 후 검증 최대 3회입니다.
필수 조회가 선택 조회보다 먼저 실행되고, 같은 gather 안의 성공 읽기만 선택 조회에서 재사용합니다.
필수 접근 조건 조회는 search_access_rules 한 번으로 모읍니다. 묶음에 포함된 직원·TF·현재 권한과
좌석 예산은 같은 분석의 개별 선택 조회에서도 재사용합니다. 직원 단독 사전 조회는 별도로 수행합니다.
새 분석은 새 묶음을 읽으며, 승인 후 실행과 권한 검증은 이 분석 캐시를 사용하지 않습니다.
선택 조회는 잘못된 범위 요청·캐시 적중도 10회 한도에 포함합니다.
이 카운터는 현재 분석 실행의 조회 한도이며 승인 대기를 포함한 전체 작업 시간 제한은 아닙니다.

검증의 영구 오류·형식 오류는 첫 오류에서 중단합니다. 일시 오류 뒤 성공하면 DONE,
3회 안에 반영이 확인되지 않으면 FAILED입니다. 검증 실패를 grant_permission 재실행으로 연결하지 않습니다.
기존 승인 계획 해시, 멱등 실행 키, DB 실행 직전 재검증·영수증 처리는 유지합니다.
readOnlyHint/idempotentHint 등 MCP annotations는 각 `@mcp.tool(annotations=...)`에 선언한 도구 설명용
힌트이며 인가 검사를 대신하지 않습니다. ContractMCP는 공유 입출력 스키마와 오류 정규화를 담당합니다.
