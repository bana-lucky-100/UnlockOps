# UnlockOps 간략 API 명세서

기준: 2026-10-20 현재 작업 폴더의 구현 코드. 실행 중인 서버를 호출한 결과가 아니라 코드에서 확인한 계약이다.
아래 예시의 `<요청 UUID>`, `<직원 UUID>`, `<자원 UUID>`, `<계획 해시>`는 실제 조회값으로 바꾼다.

## 1. 서버와 MCP의 역할

**Spring은 사용자와 승인 업무를 관리하고, MCP는 에이전트에 조회·실행 도구를 제공한다.**
MCP도 서버 프로세스다. 이 문서에서 “서버 API”는 화면이 호출하는 Spring REST API를 뜻한다.

| 구분 | 호출하는 쪽 | 담당 기능 | 데이터 접근 |
| --- | --- | --- | --- |
| Spring Backend | Vue 화면 | 로그인, 요청 접수·조회, 사람의 승인·반려, 최종 상태·이력 저장 | PostgreSQL의 사용자·요청·승인·이력 |
| LangGraph Worker | RabbitMQ 작업 큐 | 질문 분석, MCP 도구 호출, 정책 판정, 승인 대기·재개, 실행·검증 순서 제어 | SQLite 체크포인트. 업무 DB 직접 변경 없음 |
| Policy MCP | LangGraph Worker | 공통·플랫폼 규정 검색 및 원문 조회 | `data/policy_corpus.md` |
| Business MCP | LangGraph Worker | 직원·권한·예산 조회, 회사 규정 검색, 승인된 권한 변경·검증 | PostgreSQL의 모의 SaaS 테이블 및 `data/company-a-access-matrix.md` |

**현재 Business MCP는 Spring REST API를 거치지 않고 같은 PostgreSQL에 직접 접근한다.**
실제 GitHub/Jira/Slack/Notion 외부 API 연동은 모의 SaaS DB로 구현되어 있다.
Spring이 사람의 승인과 요청 상태를 기록하고, Business MCP가 실행 직전 승인 기록과 조건을 다시 확인한다.

```mermaid
flowchart TD
  UI["Vue 화면"] -->|"REST: 접수·조회·승인"| S["Spring Backend"]
  S -->|"RabbitMQ: 분석·실행 작업"| A["LangGraph Worker"]
  A -->|"MCP: 규정 검색"| P["Policy MCP"]
  A -->|"MCP: 업무 조회·권한 변경"| B["Business MCP"]
  A -->|"RabbitMQ: 진행·결과"| S
  S <-->|"요청·승인·상태"| DB[("PostgreSQL")]
  B <-->|"승인 재확인·모의 SaaS 조회/변경"| DB
```

## 2. Spring REST API — 화면용

전체 Compose 실행 시 화면과 API의 기준 주소는 `http://localhost:8088`이다.
`/api/*`가 내부 Spring `8080`으로 프록시된다. 단독 Spring 실행의 기본 주소는 `http://localhost:8080`이다.

- 인증: 로그인 세션 쿠키. POST에는 CSRF 헤더가 필요하며 **로그인 POST도 포함**한다.
- 먼저 `GET /api/auth/csrf`의 `headerName`과 `token`을 받아 이후 POST 헤더에 넣고 쿠키를 유지한다.
- 요청 JSON은 주로 camelCase, 응답의 DB 필드는 주로 snake_case다. 아래 필드명을 그대로 사용한다.
- 플랫폼: `GITHUB / JIRA / SLACK / NOTION`. 승인 담당자는 `APPROVER` 역할과 과장 이상 직급을 만족해야 한다.

| Method / Path | Request | 정상 Response | 접근 범위 |
| --- | --- | --- | --- |
| `GET /api/health` | 없음 | `200 {"status":"UP"}` | 로그인 전 가능 |
| `GET /api/auth/csrf` | 없음 | `200 {"token":"…","headerName":"X-XSRF-TOKEN"}` | 로그인 전 가능 |
| `POST /api/auth/login` | `{"loginId":"kim_dev","password":"…"}` | `200 User` + 세션 쿠키 | 로그인 전 가능. CSRF 필요 |
| `GET /api/auth/me` | 세션 쿠키 | `200 User` | 로그인 사용자 |
| `POST /api/auth/logout` | 본문 없음 | `204` 본문 없음 | 세션·CSRF 사용 |
| `POST /api/problems` | `platform`, `contents`, 선택 `simulateJiraFailure`. 선택 헤더 `Idempotency-Key` | `202 {"id":"<요청 UUID>","status":"RECEIVED"}` | 로그인 사용자 |
| `GET /api/problems?mine=true` | query: `mine=true` | `200 RequesterProblem[]` | 본인 요청 최근 100건 |
| `GET /api/problems` | `mine` 생략 또는 `false` | `200 ApproverProblem[]` | 지정 승인자에게 배정된 최근 100건. 운영 담당자는 전체 열람 |
| `GET /api/problems/{id}` | path: 요청 UUID | `200 ProblemDetail` | 본인·지정 승인자·운영 담당자 |
| `POST /api/problems/{id}/decision` | `approved`, `expectedPlanHash`, `reason` | `200 {"id":"<요청 UUID>","status":"EXECUTING 또는 REJECTED"}` | 지정 승인자만. 본인 승인 불가 |
| `GET /api/approvals/summary` | 본문 없음 | `200 {"department":"개발팀","memberCount":10,"weekRequests":5,"approved":3,"rejected":1,"failed":1}` | 승인 담당자. 값은 예시 |

### 주요 요청·응답 필드

| 형식 | 필드 |
| --- | --- |
| `User` | `id`, `login_id`, `employee_no`, `name`, `role`, `job_grade`, `job_family`, `department`. 비밀번호 해시 제외 |
| 접수 Request | `platform`: 위 4개 중 하나. `contents`: 비어 있지 않은 문자열, 최대 5,000자. `simulateJiraFailure`: 기본 false, Jira 데모에서만 true 허용. 요청자는 로그인 세션에서 서버가 결정 |
| 승인 Request | `approved`: boolean. `expectedPlanHash`: 승인 카드에서 받은 `plan_hash`. `reason`: 최대 1,000자, 반려 시 필수. **승인 대기 상태이며 해시가 일치해야 처리** |
| `RequesterProblem` | `id`, `requester_id`, `approver_id`, `platform`, `contents`, `status`, `reason_code`, `diagnosis`, `proposal`, `resource_id`, `requested_role`, `decision_reason`, `decided_at`, `verification_ok`, `created_at`, `updated_at`, `requester_name`, `employee_no` |
| `ApproverProblem` | `id`, `platform`, `contents`, `status`, `reason_code`, `diagnosis`, `proposal`, `approver_id`, `requested_role`, `plan_hash`, `verification_ok`, `agent_mode`, `created_at`, `updated_at`, `requester_name`, `employee_no` |
| `ProblemDetail`: 본인 조회 | `RequesterProblem` + 공개 `events`. 이벤트는 `{kind,payload:{message},created_at}`. `plan`, `evidence`, 해시, 내부 실행 키 제외 |
| `ProblemDetail`: 담당자 조회 | 내부 요청 필드 + `plan`, `evidence`, `plan_hash`, `approved_plan_hash`, `events` 등. 본인인 승인자는 본인 조회 형식 적용 |
| 승인 집계 | 한국 시간 이번 주 월요일 00:00부터 다음 월요일 전까지 **접수된 본인 배정 요청** 기준. `approved`와 `failed`는 중복될 수 있음 |

접수 예시:

```json
{"platform":"GITHUB","contents":"payment-core에 push가 안 됩니다","simulateJiraFailure":false}
```

접수 응답:

```json
{"id":"<요청 UUID>","status":"RECEIVED"}
```

공식 UI는 접수 시 `Idempotency-Key: <접수 키>` 헤더를 전송한다. 동일 사용자의 같은 키·같은 유효 본문은
추가 작업을 만들지 않고 최초 응답을 재사용한다. 처리 상태가 진행됐어도 재전송 응답은 최초 RECEIVED이며 최신 상태는 GET으로 확인한다.
같은 키의 다른 유효 본문은 409다. 키는 1~128자의 영문·숫자·`._:-`로 제한하며 잘못된 키는 400이다.
다른 사용자·같은 키는 독립이고, 새 키 또는 키 없는 요청은 새 접수다. 헤더 없는 클라이언트는 접수 멱등성이 적용되지 않는다.
키 수명·정규화·트랜잭션 경계는 [접수 멱등성 계약](contracts/README.md#요청-접수-멱등성)을 참고한다.

승인 요청 예시:

```json
{"approved":true,"expectedPlanHash":"<계획 해시>","reason":"업무상 필요한 접근입니다."}
```

승인 응답의 `EXECUTING`은 실행 작업 접수를 뜻한다. 실제 부여·검증 완료는 상세 조회의 `DONE`과 `verification_ok`로 확인한다.

**공통 오류:** `{"message":"오류 안내"}`. 대표 HTTP 코드는 `400` 입력 오류, `401` 로그인 필요/실패,
`403` 권한 또는 CSRF 오류, `404` 요청 없음, `409` 승인 상태·계획·조건 변경, `500` 서버 오류다.

## 3. MCP 도구 API — 에이전트용

독립 로컬 실행: Policy `http://localhost:8001/mcp`, Business `http://localhost:8002/mcp`.
Compose 내부: `http://policy-mcp:8000/mcp`, `http://business-mcp:8000/mcp`.
기본 Compose는 MCP 포트를 호스트에 공개하지 않는다.

인증은 `Authorization: Bearer <MCP_TOKEN>`이다. 두 MCP의 `GET /health`도 같은 인증을 사용하며
성공 응답은 `{"status":"UP"}`, 인증 실패는 HTTP `401 {"error":"unauthorized"}`다.

아래 이름은 REST URL이 아니라 MCP `tools/call`에서 호출하는 **도구 이름**이다.
표의 Request는 `arguments`, Response는 MCP 응답의 `structuredContent`에 해당한다.

| 담당 | 도구 이름 | Request (`arguments`) | Response 주요 필드 | 역할 |
| --- | --- | --- | --- | --- |
| Policy MCP | `search_policy` | `query`, `platform`, 선택 `limit=5` | `{hits:[Evidence]}` | 규정 유사도 검색 |
| Policy MCP | `read_policy` | `doc_id`, 선택 `article=""` | `{chunks:[Evidence]}` | 규정 원문 조회 |
| Business MCP | `get_employee_profile` | `employee_id` | `{id,employee_no,name,department_id,department_name,job_grade,job_family,head_id}` | 직원 정보 조회 |
| Business MCP | `resolve_resource` | `platform`, `hint` | `{matches:[Resource],ambiguous:boolean}` | 저장소·프로젝트 등 대상 찾기 |
| Business MCP | `get_tf_membership` | `employee_id`, `resource_id` | `{tf_id,member:boolean,leader_id}` | TF 소속·리더 조회 |
| Business MCP | `get_current_permissions` | `employee_id`, `resource_id` | `{role:string 또는 null,source,…}`. Jira는 `can_browse`, GitHub 저장소는 `teams` 추가 | 실제 현재 권한 조회 |
| Business MCP | `check_budget` | `employee_id` | `{budget:{department_id,remaining_monthly_amount,unit_monthly_price,currency,updated_at} 또는 null}` | 부서 예산·좌석 가격 조회 |
| Business MCP | `search_access_rules` | `query`, `employee_id`, `resource_id` | `{hits:[Evidence],maximum_role,rule_source,exception_source}` | 회사 규정 검색·권한 상한 계산 |
| Business MCP | `read_access_rule` | `doc_id` | `{chunks:[Evidence]}` | 회사 규정 절 원문 조회 |
| Business MCP | `grant_permission` | `problem_id`, `idempotency_key` | `{ok:true,changed:boolean,role}` | **유일한 변경 도구**, 승인된 계획 실행 |
| Business MCP | `verify_permission` | `employee_id`, `resource_id`, `requested_role` | `{ok:true,verified:boolean,current:{role,source,…}}` | 실행 후 실제 권한 재조회 |

- `employee_id`는 Spring의 `requester_id`에 해당하는 직원 UUID다. `resource_id`, `problem_id`도 UUID다.
- `Resource`의 핵심 필드: `id`, `external_id`, `name`, `platform`, `access_scope`. 부서·기밀 자원은 관련 부서 정보 포함.
- `Evidence`의 핵심 필드: `chunk_id`, `doc_id`, `text`, `source`, `version`. 검색 점수·원문 해시 등 추가 메타데이터 가능.
- `search_policy.limit`: 정수 1~10. `query`·`hint`: 최대 5,000자. 정의되지 않은 입력 필드는 거부한다.
- `read_access_rule.doc_id`: `A-ACCESS-03/04/07`. `read_policy.doc_id`: `POL-xx` 또는 `GH/JR/SL/NT-OFF-xx` 형식.
- `requested_role`: `Read / Write / Viewer / Developer / Can view / Can edit / Member / Seat`. 실제 부여 가능 여부는 별도 규정 판정.
- 예산 금액은 `"100.00"`처럼 소수점 최대 두 자리 문자열이다. `ambiguous`는 후보가 정확히 하나일 때만 false다.
- `grant_permission`의 대상·권한은 DB에 승인된 계획에서 읽는다. 호출자가 직원·자원·역할을 따로 지정하지 않는다.
- 같은 실행 키로 재호출하면 저장된 결과를 반환한다. `changed:false`는 이미 필요한 권한을 보유해 변경하지 않은 성공도 포함한다.

MCP SDK의 연결 초기화를 마친 뒤 보내는 `tools/call` 요청 예시:

```json
{
  "jsonrpc":"2.0",
  "id":1,
  "method":"tools/call",
  "params":{
    "name":"grant_permission",
    "arguments":{"problem_id":"<요청 UUID>","idempotency_key":"<서버가 발급한 실행 키>"}
  }
}
```

정상 응답 예시 (`result.content`에도 같은 JSON 텍스트가 제공됨):

```json
{
  "jsonrpc":"2.0",
  "id":1,
  "result":{
    "isError":false,
    "structuredContent":{"ok":true,"changed":true,"role":"Write"},
    "content":[{"type":"text","text":"{\"ok\":true,\"changed\":true,\"role\":\"Write\"}"}]
  }
}
```

도구 실행 오류는 `result.isError=true`와 다음 `structuredContent`로 반환한다:

```json
{"ok":false,"error":{"code":"APPROVAL_REQUIRED","message":"Business operation was not applied","retryable":false}}
```

대표 코드: `INVALID_TOOL_INPUT`, `NOT_FOUND`, `APPROVAL_REQUIRED`, `PLAN_CHANGED`,
`INVALID_EXECUTION_KEY`, `UPSTREAM_UNAVAILABLE`, `INVALID_TOOL_OUTPUT`.
업무상 거절은 재시도하지 않고, 일시 장애는 `retryable`에 따라 한도 내에서 재시도한다.

## 4. Spring ↔ Agent 사이 — RabbitMQ 메시지

Spring이 Agent를 호출하는 HTTP API는 현재 없다. RabbitMQ로 작업과 결과를 비동기 교환한다.

| 방향·routing key | Request / Message | Response / 후속 처리 |
| --- | --- | --- |
| Spring → Worker: `analysis` | `{event_id,job_type:"ANALYZE",problem_id,requester_id,platform,contents,idempotency_key:null,plan_hash:null}` | Worker가 MCP로 분석한 뒤 `results`에 결과 발행 |
| Spring → Worker: `execution` | 같은 형식에 `job_type:"EXECUTE"`. 서버가 기록한 `idempotency_key`, `plan_hash` 포함 | 저장된 승인 대기 그래프를 재개해 권한 부여·검증 실행 |
| Worker → Spring: `results` | `{event_id,problem_id,job_type,kind,…}` | Spring이 중복·상태 전이를 검사해 DB 반영. 화면은 REST로 다시 조회 |

`kind`: `PROGRESS / ANALYZED / EXECUTED / FAILED`.
`ANALYZED`·`EXECUTED`에는 `result:{status,reasonCode,summary,diagnosis,proposal,evidence,nextAction,plan,verification_ok,agent_mode}`가,
`FAILED`에는 `error_code`가 들어간다. 자세한 envelope는 [공통 계약](contracts/README.md#rabbitmq)을 참고한다.

## 5. 전체 처리 순서

1. 화면 → Spring: `POST /api/problems`로 접수. `202 RECEIVED`를 즉시 응답한다.
2. Spring → RabbitMQ → Worker: 분석 작업을 보낸다.
3. Worker → Policy/Business MCP: 규정·직원·현재 권한 등을 조회하고 처리안을 만든다.
4. Worker → Spring: 분석 결과를 반환한다. 변경이 필요하고 부여 가능하면 `WAITING_APPROVAL`로 만든다.
5. 승인자 화면 → Spring: `POST /api/problems/{id}/decision`으로 승인·반려를 기록한다.
6. 승인 시 Spring → Worker → Business MCP: 승인 내용을 재확인해 부여하고, 재조회로 검증한다.
7. Worker → Spring: 최종 결과를 반영하고 화면에서 확인한다.

상태: `RECEIVED / DIAGNOSING / WAITING_APPROVAL / EXECUTING / DONE / REJECTED / MANUAL_REVIEW / FAILED`.
추가 질문용 API는 없으며 정보 부족·대상 불명확은 `MANUAL_REVIEW`, 예산 부족은 `REJECTED`로 처리한다.

구현 참조: `backend/src/main/java/com/unlockops/`의 Controller·Service·SecurityConfig,
`mcp/unlockops_mcp/`、`agent/unlockops/contracts.py`、`worker/unlockops_worker/__main__.py`、`compose.yaml`。
상세 MCP 입출력·오류 규칙은 [MCP 계약](contracts/mcp.md)을 참고한다.
