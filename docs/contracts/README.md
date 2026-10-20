# API와 큐 계약 v2

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
| POST /api/problems | platform, contents, simulateJiraFailure(데모 Jira만). requester_id는 서버가 확정. 202 {id,status} |
| GET /api/problems | 담당자만. 지정 요청 최근 100건. 운영 담당자는 이력 전체 열람 |
| GET /api/problems?mine=true | 로그인 사용자의 본인 요청 최근 100건. 요청자용 응답 필드만 반환. APPROVER도 본인 요청 조회 가능 |
| GET /api/problems/{id} | 본인 또는 지정 담당자·운영 담당자. 본인은 공개 응답, 담당자는 기존 plan/evidence/events 포함 |
| GET /api/approvals/summary | 승인자만. 로그인 사용자에게 배정된 이번 주 요청 집계 |
| POST /api/problems/{id}/decision | approved, expectedPlanHash, reason. 지정 승인자만, 본인 승인 불가. 반려 시 reason 필수 |

요청자는 `/api/problems`(mine 생략/false) 및 승인 현황에 접근할 수 없습니다. 본인 조회 허용은 승인 권한을 부여하지 않습니다.
추가 정보를 제출하는 대화·PATCH API는 없습니다.

### 요청자 응답

명시적인 허용 목록: id, requester_id, approver_id, platform, contents, status, reason_code,
diagnosis, proposal, resource_id, requested_role, decision_reason, decided_at, verification_ok,
created_at, updated_at, requester_name, employee_no. 목록은 해당 필드, 상세는 공개 events를 추가합니다.
evidence, plan, plan_hash, approved_plan_hash, thread_id, idempotency_key 및 원본 JSON은 반환하지 않습니다.
본인이면서 APPROVER인 경우에도 본인 상세는 공개 응답을 사용합니다.

공개 이력은 `{kind, payload: {message}, created_at}` 형식입니다. 원본 도구·근거·실행 계획·내부 오류 코드를
재귀적으로 제거하는 대신 새 메시지를 구성합니다. 담당자에게는 기존 원본 이력을 제공합니다.
diagnosis/proposal의 기존 생성·저장 방식은 이번 변경에서 유지합니다.

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

## RabbitMQ

durable direct exchange `unlockops`, routing key/queue:

- `analysis` → `unlockops.analysis`: ANALYZE 작업
- `execution` → `unlockops.execution`: EXECUTE 작업
- `results` → `unlockops.results`: 에이전트 결과·진행 이벤트
- `dead` → `unlockops.dead`: 형식 오류·소비 처리 한도 초과 메시지

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
 "result":{"status":"WAITING_APPROVAL","reasonCode":"ELIGIBLE","summary":"승인이 필요합니다",
 "diagnosis":"현재 권한 부족","proposal":"Write 부여 제안","evidence":[],"nextAction":"승인 검토",
 "plan":{"problem_id":"uuid","requester_id":"uuid","platform":"GITHUB","resource_id":"uuid",
 "resource_key":"payment-core","requested_role":"Write"},"verification_ok":null,"agent_mode":"demo"}}
```

kind: PROGRESS / ANALYZED / EXECUTED / FAILED. FAILED에는 error_code가 들어갑니다.
실제 승인 대기 계획에는 빈 evidence를 허용하지 않습니다. 위 예시는 형식만 표현합니다.
모든 중복 이벤트는 무시되며, 지연된 분석 결과가 승인·완료 상태를 덮어쓰지 못합니다.
