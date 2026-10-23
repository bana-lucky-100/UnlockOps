# Phase 2 공통 계약 v2

상태: **베이스라인 4단계 — 서버·Worker·Agent·MCP·프론트 연결 구현. 지정 버전 프론트 빌드·브라우저·전체 스택 검증은 남음**.
변경 의도·검증·다음 단계는 루트 [IMPLEMENTATION.md](../../IMPLEMENTATION.md)에 누적한다.

## 원본과 생성물

- 원본: `agent/unlockops/common/phase2.py`의 엄격한 Pydantic 모델.
- `schema.json`: JSON Schema 2020-12, 구조 검증용. 상태 간 조건은 Python validator/Java Phase2Codec에서 추가 검사한다.
- `reason-status.json`: 최소 공통 사유 코드와 상태. 기존 상세 코드의 삭제/일괄 치환은 하지 않는다.
- Java: `com.unlockops.contracts.v2.Phase2Types`(생성 DTO), `Phase2Codec`(경계 검증·canonical hash).
- TypeScript: `frontend/src/contracts/phase2.ts`(생성 타입). 타입은 네트워크 응답의 런타임 검증을 대신하지 않는다.
- `examples/vectors.json`: Python/Java 공통 정상·거절 벡터 및 계획 canonical JSON/SHA-256.
- `http.json`: OpenAPI 3.1 서버 API 계약. 비동기 분석은 v2 Worker와 두 MCP를 함께 실행해야 한다.

```sh
.venv/bin/python scripts/export_phase2_contracts.py
.venv/bin/python scripts/export_phase2_contracts.py --check
.venv/bin/python scripts/generate_phase2_examples.py
```

생성된 DTO를 직접 수정하지 않는다. enum/필드는 원본을 수정하고 다시 생성한다.
Java와 Python의 의미 검증은 공유 벡터에 정상·실패 사례를 추가하여 함께 검증한다.

## 버전과 호환

v2 공개 응답·작업·이벤트·계획은 `schema_version=2`를 명시한다. 신규 필드 표기는 snake_case.
기존 v1 `Job/Result/Plan`, Java `GrantPlan/AgentResult`, frontend `api.ts`는 유지한다.
기존 ON_HOLD→REJECTED 정규화는 **v1 해석기에만** 남는다. v2는 ON_HOLD를 그대로 유지한다.
v2를 v1 해석기로 보내거나 새 플랫폼을 기존 실행기에 그대로 연결하면 안 된다.
서버 결과 리스너는 버전/작업 분기 후 v2 해석기를 선택한다. Worker도 큐/버전/작업을 검증한 뒤 별도 그래프로 분기한다. 알 수 없는 버전은 거부한다.

기존 `problems` 행의 contract_version은 1, 업무 종류는 ACCESS_REQUEST다. 과거 계획·해시·체크포인트·영수증을 다시 쓰지 않는다.
일반 안내는 이미 DONE/GUIDANCE다. v2도 이 결과 구분을 유지하며 ACCESS_VERIFIED에는 최신 검증 성공이 필요하다.
회수는 별도의 ReclaimRunView이며 result_type이나 grant plan을 강제로 넣지 않는다.

## 승인 계획과 해시

권한 하나/요청 하나. entitlement는 resource에 종속되고 플랫폼 권한을 공통 숫자 순위로 비교하지 않는다.
계획에는 company/requester/resource/entitlement와 권한 매핑·가격·정책·승인 경로 revision 및 순서 있는 approver_ids가 들어간다.
UUID는 소문자 표준 형식, 돈은 `120.00` 같은 소수점 2자리 문자열, 통화는 3자리 대문자다.
플랫 JSON 키를 알파벳순 정렬하고 공백 없이 UTF-8 직렬화한 바이트를 SHA-256 처리한다. 승인자 배열 순서는 변경하지 않는다.
v1의 6필드 해시는 그대로 두고 v2는 별도로 계산한다. 매핑·가격·정책·경로가 바뀌면 새로운 revision/계획 버전/승인이 필요하다.
DB revision 테이블은 UPDATE/DELETE를 막고 새 revision INSERT를 사용한다.

## API 설계 경계

기존 `/api/problems`의 v1 입력에 새 필드를 끼워 넣지 않도록 **승인 v2는 `/api/v2/problems`**로 제공한다.
회수는 합의한 `/api/reclaim/...`를 유지한다. 로그인/CSRF는 기존 방식 재사용.
요청자·회사·허용 조직은 서버의 세션에서 확정한다. 공개 요청에서 requester_id/company_id를 받지 않는다.
가격·승인자·plan은 클라이언트가 확정하지 않는다. 결정 입력은 action/expected_plan_hash/expected_plan_version/reason이다.
expected_plan_version은 1 이상의 필수 정수다. 승인·반려·보류 모두 현재 계획 버전과 해시를 함께 검사한다.
버전 누락·0 이하는 400, 현재 회차 또는 해시 불일치는 409다. v2 클라이언트도 함께 갱신해야 한다.
조회는 부작용이 없고, 회수 시작 POST에 Idempotency-Key를 요구한다. 같은 키/다른 입력은 409.

## 메시지 경계

| 작업 | task_type | job_type | 식별자 | 큐 |
|---|---|---|---|---|
| 승인 분석 | ACCESS_REQUEST | ANALYZE | problem_id | v2.analysis |
| 최종 승인 후 실행 | ACCESS_REQUEST | EXECUTE | problem_id·plan_hash·idempotency_key | v2.execution |
| 회수 점검 | RECLAIM_SCAN | RECLAIM_CHECK | run_id | v2.analysis |

v2 결과 봉투는 `schema_version,event_id,job_event_id,task_type,event_type`와 업무 ID 및 `result`를 가진다.
회수 상세 결과는 `targets`에 넣는다. 첨부 초안의 최상위 status/report 구조를 **공통 result 봉투**로 명시적으로 정리했다.
Worker는 raw schema_version/task_type/job_type 검증 후 분기한다. 기존 Job에 먼저 넣지 않는다.
Spring results 큐는 하나의 라우터가 분기한다. 같은 큐에 작업 종류별 경쟁 소비자를 달지 않는다.
기존 v1 메시지는 adapter로 원본을 보존하며 처리한다. v2 필드와 v1 camelCase를 한 메시지에 섞지 않는다.
회수 Worker는 최종 DONE을 보낼 수 없다. Spring이 저장·필수 알림을 확인하고 DONE을 확정한다.
event_id 중복 방지와 실행 키 멱등성, 정기 실행 중복, 후보 알림 중복은 각각 다른 제약이다.

## MCP 계약

v2 Policy MCP는 search_workflow_policy/read_workflow_policy로 작업에 연결된 서버 정책 revision만 검색·조회한다. 임시 정책 문서는 활성 v1 corpus에 추가하지 않는다.
Business MCP 신규 읽기 도구는 `get_reclaim_check_context`, `list_revocation_candidates`, `get_reclaim_notification_history`다.
요청 모델은 schema.json의 ReclaimContextRequest/CandidatePageRequest/NotificationHistoryRequest를 사용한다.
페이지는 run_id/snapshot_id/as_of/expected_count/next_cursor/items를 전달한다. cursor는 불투명 토큰이다.
Worker가 모든 페이지·개수·중복·스냅샷 일치를 확인한 뒤에만 scan_complete를 확정한다.
MCP/Worker는 업무 DB에 직접 쓰지 않는다. 회수 도구에는 grant_permission을 허용하지 않는다.

## 회수 상태·비용·알림

회수에는 승인 단계가 없다: current_step=null, total_steps=0, approval_steps=[], verification_ok=null.
scan_complete는 전체 페이지 조회 완료를 의미한다. 개별 사실 미확인은 추가 확인 목록으로 분리하며 DONE을 막지 않는다. 전체 조회 미완료·미완료 필수 알림은 DONE이 될 수 없다.
후보 status와 실행 status를 분리한다. 불확실한 행은 candidate_status=null/review_required=true.
기존 후보를 근거 없이 EXCLUDED/RETAINED로 바꾸지 않는다. 새로운 episode/target ID는 Spring이 생성한다.
Candidate DTO는 보고서 explanation/generation_mode, 정책·사실 근거, cost_impact를 가진다.
금액 UNKNOWN은 null이며 0이 아니다. 통화별로 합산하고 실제 절감/환입 완료로 표시하지 않는다.
같은 후보는 target/episode를 재사용한다. 읽음은 전달/해결과 별개이며 action_taken=NONE만 허용한다.

## 서버의 검증 책임

실제 레코드 존재·조직 범위·정책 최신성·지정 승인자·영수증·독립 조회를 Spring 서비스에서 검증한다.
불변 snapshot 행은 점검 접수 트랜잭션에서 생성·고정한다. JSON 필드 하나를 보냈다는 이유로 일관된 스냅샷이 되지 않는다.
회사 문서의 경로 단계 역할을 실제 직원으로 매핑하고 본인 승인·다른 회사 접근을 차단한다.
기존 권한 writer가 살아 있는 동안 permissions를 access_assignments로 복사한 값을 최신이라고 읽지 않는다.

## 3단계 런타임 연결 계약

- 새 명령 큐는 `unlockops.v2.analysis` / `unlockops.v2.execution`. 3단계 Worker가 기존 v1 큐와 함께 소비한다.
- 결과 큐는 기존 `unlockops.results`를 사용하며 단일 리스너가 버전/작업별로 분기한다.
- 결과의 `job_event_id`는 원래 Job의 `event_id`를 그대로 돌려준다. 결과 `event_id`는 결과 전송 식별자로 따로 발급한다.
- 서버는 현재 작업 ID와 다른 결과를 이력만 남기고 무시한다. 보류 재개 때 새 Job이 발급된다.
- 승인 결과에는 `proposed_entitlement_id`와 `policy_evidence`를 추가했다. 가격/승인자를 Worker가 확정하지 않는다.
- `AccessView`는 `plan_hash`와 `plan_version`을 추가로 제공한다. 승인 화면은 이 값을 `expected_plan_hash`와 `expected_plan_version`으로 함께 보낸다. 같은 내용의 계획도 재분석 후에는 회차가 달라지므로 이전 화면의 결정은 거절된다.

### 구현된 승인 Worker 순서

1. `/internal/v2/problems/{id}/context`로 회사 범위 내 자원·직무 사실·정책을 조회한다.
2. 요청을 분석하고 `/assessment`에 `{job_event_id, entitlement_id}`를 보내 서버의 최신 판정·계획·근거를 얻는다.
3. `AccessEvent`의 ANALYZED에 해당 판정·계획 해시와 정책 인용을 담는다. WAITING_APPROVAL의 단계는 assessment.plan.approver_ids 순서로 구성한다.
4. 서버는 같은 조건을 재검증하고 분석 해시가 현재 계획과 일치할 때 승인 계획/단계를 저장한다. 불일치는 PLAN_REVIEW_REQUIRED로 수동 검토한다. 승인 계획·금액·승인자는 서버 결과가 최종 기준이다.
5. 모든 사람이 승인하면 EXECUTE Job이 발행된다. Worker는 `/execute`에 `{job_event_id, plan_hash, idempotency_key}`를 보낸다.
6. `/verify`를 별도 HTTP 호출하여 현재 모의 제공자 상태를 읽는다. 실행 영수증만으로 성공으로 만들지 않는다.
7. EXECUTED 결과를 보낸다. Spring이 영수증과 현재 제공자 상태를 다시 확인하여 DONE/ACCESS_VERIFIED를 확정한다.

내부 API는 기존 `/internal/**` 서비스 토큰 인증을 사용한다. 공개 API는 세션/CSRF를 사용한다.
가격·승인자 역할을 임의로 전달받는 공개 API는 없다. 접수·재개와 outbox, 결과와 inbox, 모의 변경·예산·영수증은 각각 동일 트랜잭션이다.
`/execute`의 조건 변경 응답은 `{executed:false, reason_code:PLAN_REVIEW_REQUIRED}`다. 재실행하지 않고 최신 workflow를 조회한다.

### 구현된 회수 Worker 순서

1. `/internal/v2/reclaim/context`에 `{run_id}`를 보내 snapshot_id/as_of/expected_count/정책 해시를 받는다.
2. `/candidates`에 `{run_id,policy_hash,cursor}`를 보내 next_cursor가 없을 때까지 읽는다. 페이지 크기는 100이다.
3. 서버의 후보 상태·비용·근거는 유지하고 설명을 보완한다. 읽은 할당 개수/중복/스냅샷을 검증한다.
4. `/notification-history`로 해당 스냅샷 내 할당들의 이전 전달 이력을 확인할 수 있다.
5. RECLAIM_CHECKED에 **제외·유지·미확인 행을 포함한 전체 items**를 targets로 보낸다. snapshot/as_of를 그대로 반영한다.
6. 전체 조회가 끝나면 미확인 행이 있어도 EXECUTING/SCAN_IN_PROGRESS로 보낸다. Worker는 DONE을 보내지 않는다. 서버가 후보·추가 확인을 저장하고 필수 알림 완료 후 DONE으로 확정한다.
7. Spring이 스냅샷과 판정을 비교하고 발생 건을 재사용하며 IN_APP 알림을 저장한 뒤 최종 상태를 확정한다.

`/api/reclaim/runs/{id}/items`로 미확인 행도 볼 수 있다. `/notifications`는 본인 알림 ID와 read_at을 제공하고 PATCH read는 최초 읽음 시각을 보존한다.
범위 내 모든 플랫폼을 담당하는 RECLAIM_REVIEWER 또는 IT_HEAD만 전체 실행을 조회/시작할 수 있다.
플랫폼별 담당자는 자기 플랫폼의 후보·알림을 볼 수 있다. B사 통합 수동 시연은 `p2_b_it_head`로 접수한다.
다른 키로 같은 scope를 동시에 시작하면 409다. 같은 키 재시도는 해당 실행을 반환한다.

### 모의 제공자와 운영 범위

v2는 `access_assignments` + `mock_entitlement_memberships`를 함께 기록한다.
v1은 LEGACY 회사의 기존 permissions/GitHub 팀/Jira 스킴을 계속 소유한다. v2 상태를 v1 테이블로 복사하지 않는다.
이전 v1 조회·실행 API에서는 v2 회사 자원을 제외한다. 플랫폼별 실제 제공자 연동은 후속 adapter 작업이다.
직무·유휴 판정은 합성 정책용 baseline 규칙이다. 새 문서 내용을 자동으로 해석해 실행 규칙을 바꾸는 기능은 아직 없다.
참고 문서를 갱신할 때 정책/가격/매핑 revision 및 구조화된 규칙도 함께 검토해야 한다.

정기 점검은 09:00 KST이며 환경변수와 scope.enabled가 모두 켜져 있어야 한다. 기본값은 비활성이다.
수동 시연/모의 권한 변경은 DEMO_ENABLED=true일 때만 허용한다. 실 SaaS 변경·회수·예산 환입은 구현하지 않는다.

### v2 도구와 체크포인트 구현

도구 입출력은 `agent/unlockops/common/phase2_tools.py`가 원본이며 MCP discovery에서 같은 스키마를 노출한다.
승인 도구는 get_access_request_context/assess_access_request/execute_access_plan/verify_access_plan이다.
분석·실행·회수마다 허용 도구와 작업 ID를 고정하고 회수에는 변경 도구를 허용하지 않는다.
완료 이벤트는 job event_id에서 결정적으로 생성하고 SQLite에 저장한 뒤 발행한다. 재전달은 저장 결과만 재발행한다.
v2 체크포인트는 작업 종류·업무 ID·명령·event_id별로 분리하고 실행 그래프는 분석 체크포인트 없이 서버 승인 계획을 새로 읽는다.
회수 기본 상한은 500행과 결과 2,000,000바이트이며 초과는 수동 검토다.

## 4단계 화면 조회

기존 AccessView/승인 입력/큐 계약은 유지한다. 화면용 GET /api/v2/problems/summaries와 /catalog를 추가한다.
summaries는 workflow·contents·platform·requester_id·requester_name·created_at을 반환하며 기존 목록 ACL을 재사용한다.
catalog는 현재 회사의 entitlement_id·resource_id·platform·resource_name·resource_key·entitlement_code·kind를 반환한다.
report에는 platform/requester_id/requester_name/created_at/approvers(id,name)/resource_name/entitlement_code를 추가한다.
인증 profile의 workflow_version/can_reclaim은 메뉴/화면 안내용이며 업무 API의 ACL을 대체하지 않는다.

## 시나리오 v4 정합화 (2026-10-23)

- 회수에는 MANUAL_REVIEW를 사용하지 않는다. 신규 후보 또는 추가 확인이 있으면 DONE/SCAN_COMPLETED, 둘 다 0건이면 DONE/NO_NEW_CANDIDATES다. 필수 알림 미완료는 FAILED/NOTIFICATION_FAILED다.
- 실행 응답은 `summary.{needs_review_count,new_candidate_count,pending_notification_count}`와 `needs_review[{assignment_id,employee_name,resource_name,missing[]}]`를 제공한다. 기존 최상위 카운트는 호환성을 위해 유지하며 summary와 일치해야 한다. Worker 이벤트에서는 summary/needs_review를 생략할 수 있고 서버가 고정 사실에서 생성한다.
- missing 코드는 USAGE_OBSERVATION(최신 사용 이력), PRICE_EVIDENCE(비용 근거), EMPLOYMENT_STATUS(재직 상태), RECLAIM_FACTS(기타 필수 사실)다. 미확인 항목은 candidate_status=null/review_required=true로 보존하고 알림을 보내지 않는다.
- 내부 QUEUED/RUNNING/REPORT_READY/PARTIAL 상태를 새로 저장하지 않는다. 현재 구현은 공통 상태를 직접 사용한다. 전체 조회 실패·상한 초과·일부 조회는 FAILED/SCAN_FAILED, scan_complete=false다. 수신된 검증 가능 부분 행은 실행 items로 저장할 수 있지만 후보 확정·알림을 수행하지 않는다. 메시지 상한을 넘으면 부분 행 전달을 생략하며 완료나 0건으로 표시하지 않는다.
- 재시도 가능한 회수 읽기 도구 호출은 기존 호출 한도 안에서 최대 3회 시도한다. 새로운 점검은 새 run_id로 기록한다. 기본 알림은 IN_APP이며 목록 저장 성공이 전달 성공이다. 외부 Slack/메일 전달은 구현 범위가 아니다.
- PLAN_REVIEW_REQUIRED와 ANALYSIS_CONFLICT는 승인 요청의 MANUAL_REVIEW 사유로 등록했다. ALREADY_HAS_ACCESS는 기존처럼 DONE/GUIDANCE/verification_ok=null이다.
- API와 Worker, MCP, 프론트 및 V8 migration은 함께 배포해야 한다. 기존 회수 MANUAL_REVIEW 이력은 V8에서 조회·알림 완료 여부에 따라 DONE 또는 FAILED로 옮긴다. 기존 정책·가격 revision과 스냅샷 원문은 수정하지 않는다.
