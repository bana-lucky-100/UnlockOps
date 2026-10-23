# API와 큐 계약 v3

Agent와 두 MCP 서버 사이의 도구별 입출력·오류 형식은 [MCP 도구 계약](mcp.md)에 정리합니다.

상태 이름은 Spring `ProblemStatus`, Python `Status`, Vue `Status`, DB CHECK에서 동일하게 사용합니다.
`RECEIVED / DIAGNOSING / WAITING_APPROVAL / EXECUTING / DONE / REJECTED / MANUAL_REVIEW / FAILED`.
되묻기 상태, PARTIAL_FAILED는 없습니다.

## HTTP (같은 출처, 세션 쿠키·CSRF)

| 요청 | 입력·권한·출력 |
|---|---|
| GET /api/auth/csrf | 인증 전 가능. token/headerName 반환 |
| POST /api/auth/login | loginId/password. 성공 시 세션 회전 및 안전한 사용자 프로필 반환 |
| GET /api/auth/me | 비밀번호 해시 없는 로그인 사용자 |
| POST /api/auth/logout | CSRF 필수, 세션 만료 |
| POST /api/problems | platform, contents, simulateJiraFailure(데모 Jira만). 선택 Idempotency-Key 헤더. requester_id는 서버가 확정. 202 {id,status} |
| GET /api/problems | 담당자만. 지정 요청 최근 100건. 운영 담당자는 이력 전체 열람 |
| GET /api/problems?mine=true | 로그인 사용자의 본인 요청 최근 100건. 요청자용 응답 필드만 반환. APPROVER도 본인 요청 조회 가능 |
| GET /api/problems/{id} | 본인 또는 지정 담당자·운영 담당자. 본인은 공개 응답, 담당자는 기존 plan/evidence/events 포함 |
| GET /api/approvals/summary | 승인자만. 로그인 사용자에게 배정된 이번 주 요청 집계 |
| POST /api/problems/{id}/decision | approved, expectedPlanHash, reason. 지정 승인자만, 본인 승인 불가. 반려 시 reason 필수 |

요청자는 `/api/problems`(mine 생략/false) 및 승인 현황에 접근할 수 없습니다. 본인 조회 허용은 승인 권한을 부여하지 않습니다.
추가 정보를 제출하는 대화·PATCH API는 없습니다.

### 요청 접수 멱등성

`POST /api/problems`는 선택 헤더 `Idempotency-Key`를 지원합니다. 공식 UI는 항상 전송하며,
응답 유실·네트워크 오류 후 같은 접수를 재시도할 때 동일한 키를 사용합니다.

- 키는 대소문자를 구분하는 1~128자의 영문·숫자·`._:-` 문자열입니다. 잘못된 값은 400이며 공백을 자동 제거하지 않습니다.
- 범위는 **로그인 사용자 ID + 접수 키**입니다. 다른 사용자의 같은 키는 독립이며 요청자 ID를 본문으로 지정할 수 없습니다.
- 같은 키와 같은 유효 입력(`platform`, 서버에서 strip한 `contents`, 기본값 false를 적용한 `simulateJiraFailure`)은
  최초 `202 {id,status:RECEIVED}`를 그대로 재사용합니다. 현재 업무 상태는 바꾸지 않으며 GET으로 조회합니다.
- 같은 사용자의 키를 다른 유효 입력에 재사용하면 409와 `{message}` 오류를 반환합니다. 기존 요청과 outbox는 수정하지 않습니다.
- 동시 요청은 DB UNIQUE 인덱스와 원자적 INSERT로 판정하고, 요청 생성에 성공한 트랜잭션만 ANALYZE outbox를 저장합니다.
  요청·접수 키·outbox 저장은 함께 커밋/롤백됩니다. 키는 요청 행이 보존되는 동안 유효하며 서버 재기동에도 유지됩니다.
- 키 없는 기존 클라이언트는 이전처럼 매번 새 요청을 생성합니다. 새 키로 같은 본문을 보내는 것도 새로운 접수입니다.
- `client_request_key`는 내부 저장 값으로 API 응답이나 worker 메시지에 추가하지 않습니다.
  기존 `idempotency_key`는 승인 후 권한 부여용 실행 키이며 별개입니다.

이 기능은 중복 **작업 생성**을 방지합니다. RabbitMQ 재전달이나 Agent 호출 자체의 정확히 한 번 실행을 보장하지 않습니다.

### 요청자 응답

명시적인 허용 목록: id, requester_id, approver_id, platform, contents, status, result_type, reason_code,
diagnosis, proposal, resource_id, requested_role, decision_reason, decided_at, verification_ok,
created_at, updated_at, requester_name, employee_no. 목록은 해당 필드, 상세는 공개 events를 추가합니다.
evidence, plan, plan_hash, approved_plan_hash, thread_id, idempotency_key 및 원본 JSON은 반환하지 않습니다.
본인이면서 APPROVER인 경우에도 본인 상세는 공개 응답을 사용합니다.

공개 이력은 `{kind, payload: {message}, created_at}` 형식입니다. 원본 도구·근거·실행 계획·내부 오류 코드를
재귀적으로 제거하는 대신 새 메시지를 구성합니다. 담당자에게는 기존 원본 이력을 제공합니다.
안내 결과의 proposal에는 답변과 출처 청크 ID를 포함하며 원본 evidence나 내부 실행 정보는 노출하지 않습니다.

### 내 승인 현황 · 이번 주

응답: `{department, memberCount, weekRequests, approved, rejected, failed}`.
department와 memberCount는 승인자의 현재 소속 부서와 해당 부서 구성원 수이며 프로필 정보입니다.
나머지 카운터는 모두 **한국 시간 월요일 00:00 이상, 다음 월요일 00:00 미만에 접수되고 p.approver_id가 로그인 사용자 ID인 요청** 기준입니다. 요청자 소속 부서는 집계 조건에 사용하지 않습니다.
approved는 사람 승인 기록(approved_plan_hash와 decided_by)이 있는 요청, rejected는 AI 자동 거절을 포함한 현재 REJECTED,
failed는 현재 FAILED입니다. 승인 후 실패하면 approved와 failed에 둘 다 포함되므로 합산해 전체 건수로 사용하지 않습니다.
일반 승인자의 목록과 동일한 배정 기준을 사용하되 요약은 이번 주 전체 건수, 목록은 기간 제한 없이 최근 100건입니다. 승인 시각이 아니라 접수 시각 기준이므로 지난주 접수·이번 주 승인 요청은 제외됩니다.
운영 담당자 song_ops의 목록은 전체 열람 예외를 유지하지만, 요약은 본인에게 배정된 요청만 집계합니다. API 응답 필드와 인증·인가 규칙은 유지합니다.

### 상태 변경과 이전 버전 호환

예산 부족 S4는 `REJECTED / BUDGET_INSUFFICIENT`이며 예산 증액 후 새 요청을 접수합니다.
V3 마이그레이션은 기존 ON_HOLD 행과 INSUFFICIENT_BUDGET 코드를 변환하고 상태 CHECK를 8개로 바꿉니다.
적용된 V1/V2와 감사 이력은 수정하지 않습니다. 구 큐 결과·체크포인트는 Python 발행 및 Spring 수신 시 새 상태·코드로 정규화합니다.

RAG 안내 성공은 `DONE / result_type=GUIDANCE / reasonCode=RAG_GUIDANCE`로 전달합니다. plan·verification_ok는 null이며
proposal에 안내문과 출처 ID를 담습니다. evidence에는 원문 청크와
`{kind:"answer_citation",chunk_id,quote}` 인용 항목을 보존하고, 인용·내용 검증은 에이전트에서 수행합니다.
검색 근거·생성 내용이 불충분해도 MANUAL_REVIEW로 처리하되 reasonCode로 구분합니다.
답변 생성·검토 단계의 모델 호출 장애는 경로별로 처리합니다.

- 일반 안내 경로: answer_node가 장애를 처리하고 `MANUAL_REVIEW / MODEL_UNAVAILABLE`을 반환합니다.
- 승인·거절·수동 검토 경로: compose_response_node가 장애를 처리하고 기존 판정과 고정 안내를 유지합니다.
  상태·reasonCode·승인 계획은 변경하지 않으며, 결과가 FAILED로 전환되지 않습니다.
- 노드에서 처리하지 않고 worker까지 전달된 모델·도구 호출 장애는 `FAILED`로 처리합니다.
  규정 오류·권한 제안 모델 오류 등 별도로 수동 검토로 전환하는 경우는 각 단계의 규칙을 따릅니다.

따라서 답변 모델 장애를 FAILED 상태만으로 집계하지 않습니다. 일반 안내는
`MANUAL_REVIEW / MODEL_UNAVAILABLE`, 기존 판정 유지 경로는 compose_response 진행 이벤트의
`grounded=false`, `reason_code=MODEL_UNAVAILABLE`로 구분합니다.
내부 handling=ANSWER는 답변 생성 경로를 뜻하며
외부 상태의 완료를 뜻하지 않습니다. 생성·검증을 통과해야 DONE / GUIDANCE가 됩니다.

| status | result_type | 의미·검증 |
|---|---|---|
| DONE | GUIDANCE | 안내 제공 완료. 비어 있지 않은 proposal, plan·verification_ok=null |
| DONE | ACCESS_VERIFIED | 실제 권한 확인 완료. verification_ok=true; EXECUTE 작업이면 실행 영수증 필수 |
| 그 외 상태 | null | 진행·대기·거절·검토·실패. 사유는 reason_code(큐에서는 reasonCode)로 구분 |

새 결과의 DONE에는 result_type이 필수입니다. 실행 작업은 GUIDANCE로 완료할 수 없습니다.
V5는 기존 안내 성공 행을 DONE / GUIDANCE로, 기존 DONE을 ACCESS_VERIFIED로 변환합니다.
원본 감사 이벤트는 수정하지 않습니다. 이전 큐·체크포인트에서 result_type 필드가 없는 경우에만
유효한 구 안내 성공(본문 있음, 계획·검증 값 없음)과 verification_ok=true인 DONE을 정규화합니다.
빈 안내 본문은 완료로 승격하지 않습니다. 서버를 V5와 함께 먼저 배포한 뒤 새 worker·프론트를 배포해야 합니다.
구 worker 메시지는 새 서버가 수신할 수 있지만 새 GUIDANCE 메시지는 구 서버가 수신할 수 없습니다.

### 승인 처리 책임

기존 decision API의 입력·응답은 유지합니다. ApprovalDecisionService는 권한·자격을 검증하고 사람 결정을 기록합니다.
ApprovedExecutionService는 저장된 요청을 다시 잠금 조회하고 ApprovalCompletionPolicy의 승인 완료 판정,
지정 승인자·계획 해시·실행 키를 검사한 뒤 EXECUTING으로 전환하고 EXECUTE outbox를 저장합니다.
두 서비스는 같은 트랜잭션을 사용하며 실행 서비스는 MANDATORY로 단독 트랜잭션 없는 호출을 막습니다.
현재 필수 승인은 한 번입니다. Phase 2의 단계별 승인 저장·배정과 정책 확장은 별도 구현이며,
이 리팩터링 자체가 다단계 승인을 제공하지는 않습니다.

## RabbitMQ

durable direct exchange `unlockops`, routing key/queue:

- `analysis` → `unlockops.analysis`: ANALYZE 작업
- `execution` → `unlockops.execution`: EXECUTE 작업
- `results` → `unlockops.results`: 에이전트 결과·진행 이벤트
- `dead` → `unlockops.dead`: 형식 오류·소비 처리 한도 초과 메시지

Backend results 소비는 확인된 일시 DB 예외만 재시도합니다(기본 최초 포함 3회, 실패 후 1초·2초 대기).
메시지 형식·결과 상태·완료 검증 위반, 명확한 비일시 DB 오류와 미분류 오류는 추가 시도 없이 dead로 보냅니다.
일시 오류도 시도 소진 후 dead로 보냅니다. DLQ 전체를 자동 재발행하지 않으며, 원인 수정 후 담당자가 재처리 여부를 판단합니다.
DLQ 이동은 업무 FAILED 전환과 별개이고, ACK 전 프로세스 종료의 원래 큐 재전달과도 구분합니다.
메시지 body/event_id와 inbox·감사·상태 변경의 트랜잭션, 완료 시 verification/실행 영수증 조건은 유지합니다.
계획/정책 검증 실패는 기존 MANUAL_REVIEW이지만, 그 과정의 DB 장애를 이 상태로 오인 처리하지 않습니다.
구체적인 분류와 검증·캡처 범위는 [재시도 안내](../messaging-retry.md)를 참고하세요.

작업 형식:

```json
{"event_id":"uuid","job_type":"ANALYZE","problem_id":"uuid","requester_id":"uuid",
 "platform":"GITHUB","contents":"payment-core에 push가 안 됩니다", "idempotency_key":null,"plan_hash":null}
```

EXECUTE에는 서버가 기록한 idempotency_key와 plan_hash가 들어갑니다. 실행 대상·역할은 큐 메시지에서
새로 만들지 않고 체크포인트/승인 DB 계획과 비교합니다.

결과 envelope:

```json
{"event_id":"uuid","problem_id":"uuid","job_type":"ANALYZE","kind":"ANALYZED",
 "result":{"status":"WAITING_APPROVAL","result_type":null,"reasonCode":"ELIGIBLE","summary":"승인이 필요합니다",
 "diagnosis":"현재 권한 부족","proposal":"Write 부여 제안","evidence":[],"nextAction":"승인 검토",
 "plan":{"problem_id":"uuid","requester_id":"uuid","platform":"GITHUB","resource_id":"uuid",
 "resource_key":"payment-core","requested_role":"Write"},"verification_ok":null,"agent_mode":"demo"}}
```

kind: PROGRESS / ANALYZED / EXECUTED / FAILED. FAILED에는 error_code가 들어갑니다.
실제 승인 대기 계획에는 빈 evidence를 허용하지 않습니다. 위 예시는 형식만 표현합니다.
모든 중복 이벤트는 무시되며, 지연된 분석 결과가 승인·완료 상태를 덮어쓰지 못합니다.

### 권한 정책과 LLM 제안

`search_access_rules`는 기존 필드에 현재 두 규정 문서의 `source_hashes`를 추가로 반환합니다.
권한 전용 LLM 제안은 `{decision, requested_role, reason, evidence_ids}`이며 `decision`은
`PROPOSE` 또는 `MANUAL_REVIEW`입니다. RAG의 실제 `chunk_id`를 인용해야 하고 명시된 요청 역할을
임의로 변경할 수 없습니다. 제안은 내부 체크포인트와 judge 진행 이벤트에 기록합니다.
결과 envelope와 여섯 필드의 `plan`·해시 형식은 유지합니다.

제안 모델 장애·응답 형식 오류·허위 인용·역할 변경·정책 근거 버전 불일치는 수동 검토로 종료합니다.
실행 직전 MCP도 DB에 저장된 근거와 현재 정책·자격을 재검증하며 실패 시 쓰기를 수행하지 않습니다.
