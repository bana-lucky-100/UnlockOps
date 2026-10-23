# 모의 권한 회수 API — 프론트 전달 계약

이슈 [#56](https://github.com/bana-lucky-100/UnlockOps/issues/56). 프론트 요청 5개 항목에 맞춘 최종 계약이다. 화면·버튼·프론트 호출 코드는 포함하지 않는다.
[HTTP 스키마](../contracts/phase2/http.json), [데이터 스키마](../contracts/phase2/schema.json), [자동 생성 TypeScript 타입](../frontend/src/contracts/phase2.ts)을 함께 참고한다.

## 1. 프론트 연동 순서

1. `GET /api/reclaim/overview`에서 targets를 표시한다. 타입은 기존 ReclaimCandidate 대신 **ReclaimTargetView**를 사용한다.
2. `candidate_status=PENDING_REVIEW`이고 `can_revoke=true`인 행에서만 회수 버튼을 활성화한다. target_id가 실제 후보 ID이며 assignment_id로 대체하지 않는다.
3. 담당자 확정 시 **POST `/api/reclaim/targets/{target_id}/revoke`, JSON 본문 `{}`, Idempotency-Key 헤더**를 보낸다.
4. 성공 200이면 overview를 다시 조회한다. 해당 행은 목록에 남고 `candidate_status=RECLAIMED`, `action_taken=REVOKED`, `can_revoke=false`, `reclaimed_at`이 채워진다.
5. 409이면 overview를 재조회해 완료/변경 상태를 반영한다. 이미 처리된 후보는 **같은 키로 재전송해도 409**다.

사유·schema_version·expected_episode_id·expected_review_run_id는 요청하지 않는다. 서버가 세션과 대상 후보에서 실행 주체·최신 점검·근거를 확정한다.
별도 execution 조회는 선택 기능이다. 버튼을 사용하려고 먼저 호출할 필요가 없다.

## 2. overview targets 데이터

기존 필드(assignment_id, target_id, episode_id, platform, 후보 사유·정책/사실 근거·비용·알림/읽음·설명)를 유지하고 현재 실행 필드를 제공한다.

| 필드 | 타입 / 의미 |
| --- | --- |
| candidate_status | PENDING_REVIEW / RETAINED / EXCLUDED / **RECLAIMED** |
| can_revoke | boolean. 담당자 실행 권한·demo/mock·ACTIVE SEAT·최신 확정 판정·현재 정책/사용/TF/유지 승인 조건을 모두 충족할 때만 true |
| reclaimed_at | 시간대가 있는 ISO 8601 문자열 또는 null. RECLAIMED일 때만 존재 |
| action_taken | NONE / REVOKED. RECLAIMED이면 REVOKED |
| employee_name / resource_name | 서버가 조회한 대상 이름과 좌석 이름 |

회수 전 예시(그 밖의 기존 근거/비용 필드는 생략):

```json
{
  "target_id": "e6b04385-a16d-501a-99ee-809760daf458",
  "assignment_id": "2c1922f4-234b-5126-8ddc-9a3bdf702237",
  "candidate_status": "PENDING_REVIEW",
  "can_revoke": true,
  "action_taken": "NONE",
  "reclaimed_at": null,
  "employee_name": "회수 R-04",
  "resource_name": "Phase 2 A GITHUB"
}
```

회수 후 해당 행의 변경 필드:

```json
{
  "candidate_status": "RECLAIMED",
  "can_revoke": false,
  "action_taken": "REVOKED",
  "reclaimed_at": "2026-10-23T16:00:00+09:00"
}
```

- review_target_count, unknown_cost_target_count, monthly_saving_by_currency는 아직 회수하지 않은 PENDING_REVIEW만 집계한다.
- 신규 후보/신규 알림 수는 해당 점검 시점의 집계이며, 회수 후 과거 점검 건수를 다시 쓰지 않는다.
- 기존 GET `/targets/{id}`와 `/runs/{id}/items`는 **점검 당시 보고서**다. 그곳의 과거 PENDING_REVIEW/action_taken=NONE을 현재 회수 상태로 해석하지 않는다.
- overview의 설명은 현재 상태를 반영한다. 회수 전에는 담당자 확정 후 회수할 수 있음을, 회수 후에는 모의 회수 완료를 표시한다.

## 3. 회수 요청과 응답

```http
POST /api/reclaim/targets/e6b04385-a16d-501a-99ee-809760daf458/revoke
Content-Type: application/json
Idempotency-Key: <새 UUID>
<기존 CSRF 헤더>: <토큰>

{}
```

로그인 세션 쿠키를 사용하고, CSRF 토큰은 기존 `/api/auth/csrf` 응답의 headerName/token으로 전달한다.
본문은 빈 JSON 객체이며 임의의 actor/company/직원/가격/성공 여부를 추가하면 400이다. 키는 공백 아닌 1~128자이며 UUID를 권장한다.

성공 200은 **ReclaimExecutionReceipt**다.

| 필드 | 타입 / 의미 |
| --- | --- |
| schema_version | 정수 2 |
| id | 회수 영수증 UUID |
| target_id / assignment_id / episode_id / review_run_id | 실행 대상 및 서버가 확인한 최신 점검 UUID |
| employee_name / resource_name | 실행 시점 대상 이름과 좌석 이름 |
| executed_by / executed_by_name | 세션에서 확정한 담당자 UUID/이름 |
| executed_at | 시간대가 있는 ISO 8601 문자열. overview reclaimed_at과 같은 실행 시각 |
| reason | 서버가 저장한 `담당자 확정으로 모의 권한 회수`. 사용자 사유 입력은 필요 없음 |
| verification_ok | true |
| assignment_status_before / assignment_status_after | ACTIVE / INACTIVE |
| provider_present_before / provider_present_after | 실행 전 제공자 권한 존재 여부 / false |
| policy_revision / policy_hash | 실행 직전 정책 revision과 SHA-256 |
| current_facts | 실행 직전 사실 원본 JSON. 감사용이며 화면의 고정 필드로 파싱하지 않음 |

일부 합성 시드는 제공자 멤버십이 처음부터 없어 provider_present_before=false다. 내부 ACTIVE 할당 종료와 최종 부재를 검증한 정상 성공이다.
영수증의 verification_ok는 실행 시점의 기록이며, 나중에 다시 승인해 새 할당을 받아도 과거 영수증은 유지된다.

## 4. 권한과 오류

- 조회는 ACTIVE APPROVER의 같은 회사·현재 대상 직원 부서·SaaS 플랫폼 RECLAIM_REVIEWER 또는 IT_HEAD 매핑을 검사한다.
- 실행은 조회 권한에 더해 같은 범위 SAAS_OPERATOR 또는 IT_HEAD가 필요하다. 조회만 가능한 담당자는 can_revoke=false다.
- 실행은 DEMO_ENABLED=true, 회사 is_mock=true에서만 가능하다. 서비스 토큰으로 공개 실행을 대신할 수 없다.

| HTTP | 처리 |
| --- | --- |
| 200 | DB 권한 종료·제공자 부재 재조회·후보 종결·영수증 저장 완료. overview 갱신 |
| 400 | 빈 객체 외 입력, 헤더/UUID/cursor 오류 |
| 401 | 로그인 필요 |
| 403 | 담당 범위·실행 권한·재직·demo/mock·CSRF 조건 위반 |
| 404 | 후보 없음 |
| 409 | 이미 처리됨, 요청 키 충돌, 최신 근거 미확인/조건 변경. 재조회 후 반영 |
| 500 | 저장/검증 장애. 성공으로 표시하지 말고 현재 상태 재조회 |

일반 오류는 `{ "message": "..." }`, 회수 409는 ReclaimExecutionError다.

```json
{
  "message": "이미 모의 회수가 완료되었습니다. 완료 이력을 확인해 주세요.",
  "code": "ALREADY_REVOKED",
  "receipt_id": "c23c9b68-f56b-45d9-b75f-c0978512bb78"
}
```

- ALREADY_REVOKED: 같은 키/다른 키 모두 이미 완료된 할당이면 409. receipt_id로 완료 기록을 식별한다.
- IDEMPOTENCY_CONFLICT: 같은 사용자·회사에서 같은 키를 다른 target에 사용함. 409.
- CANDIDATE_CHANGED / RECHECK_REQUIRED: 사용 재개, 유지 승인, 최신 점검 진행/실패/추가 확인 등. 409이며 receipt_id=null.
- EXECUTION_FORBIDDEN / MOCK_ONLY도 실행 직전 조건 변경을 나타낼 수 있다. 일반 권한 거절은 403이다.
- 응답 유실 시 동일 키·같은 target·같은 `{}`로 재전송한다. 미완료였다면 200, 이미 커밋됐다면 409 후 overview/영수증으로 확인한다. 자동으로 키를 바꿔 재실행하지 않는다.

## 5. 선택 조회 API

- `GET /api/reclaim/targets/{id}/execution`: ReclaimExecutionState. 현재 할당 상태·can_revoke·block_reason·NOT_EXECUTED/SUCCEEDED·영수증을 제공한다. 버튼 연동의 필수 선행 호출은 아니다.
- `GET /api/reclaim/executions?cursor=0`: ReclaimExecutionPage `{schema_version:2,items:[영수증],next_cursor:null|정수}`. 현재 담당 범위에서 최근순 최대 50개를 반환한다.
- cursor는 0 이상 offset이며 next_cursor를 다음 요청에 사용한다. 신규 기록으로 페이지 경계가 움직일 수 있으므로 영수증 id로 중복을 구분한다.

## 6. DB 및 재신청 계약

- V10은 candidate_status CHECK에 RECLAIMED, action_taken CHECK에 REVOKED를 허용하고 reclaimed_at 및 불변 회수 영수증을 추가한다. 아직 배포하지 않은 이번 신규 마이그레이션이며 적용된 V1~V9는 수정하지 않는다.
- 한 트랜잭션에서 모의 제공자 멤버십 삭제, access_assignments ACTIVE→INACTIVE/ended_at, 열린 후보 RECLAIMED/reclaimed_at/closed_at, 해당 점검 행의 후속 action_taken=REVOKED, 독립 SELECT 검증, 영수증 저장을 처리한다. 중간 실패는 전체 롤백한다.
- 이미 보유/중복 좌석 판정은 ACTIVE 할당만 조회한다. 회수된 할당은 판정에서 빠져 **동일 좌석 재신청 시 최신 정책·예산에 따라 새로운 승인 흐름**으로 진행한다. 기존 완료 요청을 재실행하는 것은 아니다.
- 예산 자동 환입은 하지 않는다. 외부 SaaS·자동/일괄 회수·회수 취소는 범위 밖이다.
- 스냅샷·원본 점검 보고서 JSON·알림/읽음·기존 부여 영수증은 보존한다. 현재 목록 모델 ReclaimTargetView와 Worker의 점검 모델 ReclaimCandidate를 구분해 Agent가 회수 완료를 주장하지 못하게 한다.
- 늦은 점검 결과는 회수한 후보/알림을 재생성하지 않고 원본 판정과 회수 영수증 참조를 남긴다. 이후 새 점검은 INACTIVE 할당을 제외한다.
- 서버 후보 템플릿과 Agent 작성 지침의 후속 처리는 `담당자가 근거를 확인한 뒤 회수할 수 있습니다.`로 변경했다.

## 7. 검증 범위

초기 설계의 테스트 실행 결과는 Java 단위43/DB·브로커18/Python247 통과다. **이는 이번 최종 프론트 계약 변경의 통과 결과가 아니다.**
사용자 요청에 따라 추가 테스트는 실행하지 않았다. 빈 본문·이미 처리 시409·overview 회수 상태에 맞춰 회귀 테스트와 계약 벡터는 갱신했으나 실행 결과는 미검증이다.
전체 스택 평가는 환경 오류로 미완료이며, 실제 SaaS/LLM/브라우저 클릭도 미검증이다. 사용자 개발 DB에는 적용하지 않았다.
