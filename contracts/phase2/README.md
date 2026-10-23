# 공통 업무 계약 v2

현재 서버·Worker·승인/회수 에이전트·MCP가 사용하는 단일 계약입니다. 폴더·큐·프론트 타입의 기존 이름은 호환을 위해 유지하며 별도의 구 실행기는 없습니다.

| 원본·생성물 | 역할 |
|---|---|
| `agent/unlockops/common/workflow_contracts.py` | 업무·계획·이벤트·완료 모델과 의미 검증 |
| `agent/unlockops/common/tool_contracts.py`, `contracts.py` | MCP 도구 모델·단일 registry·공통 오류 |
| `schema.json`, `reason-status.json` | 생성된 구조·사유 코드 계약 |
| Java `WorkflowTypes`, `WorkflowCodec` | 생성 DTO와 서버 의미 검증·canonical hash |
| `frontend/src/contracts/phase2.ts` | 기존 프론트와 동일한 생성 타입 |
| `examples/vectors.json` | Python/Java 공통 정상·실패 벡터와 hash 기준 |
| `http.json` | 공개·내부 API 계약 |

```sh
.venv/bin/python scripts/export_phase2_contracts.py --check
.venv/bin/python scripts/export_phase2_http.py --check
```

필드·enum은 원본을 수정해 생성합니다. TS 타입만으로 런타임 검증을 대신하지 않습니다.
모든 업무·작업·결과는 schema_version=2를 명시합니다. snake_case와 기존 공개 API를 유지합니다.

**승인 계획과 결정**

계획은 company/requester/resource/entitlement, 권한 매핑·가격·정책·승인 경로 revision, 순서 있는 approver_ids를 포함합니다.
UUID는 표준 소문자, 금액은 소수점 2자리 문자열, 통화는 3자리 대문자입니다.
JSON 키를 정렬해 공백 없이 UTF-8 직렬화하고 SHA-256을 계산합니다. 승인자 배열 순서는 보존합니다.
계획·revision을 덮어쓰지 않으며 조건 변경과 재분석은 새 계획 버전과 재승인을 요구합니다.

결정 입력은 action(APPROVE/REJECT/HOLD), expected_plan_hash, expected_plan_version, reason입니다.
현재 단계 당사자만 결정하며 본인 승인·승인 순서 우회·다른 회사 접근을 차단합니다.
계획 버전 누락·0 이하는 400, 현재 해시/버전·상태 충돌은 409, 권한 위반은 403입니다.
REJECT/HOLD는 사유가 필수이며 ON_HOLD를 REJECTED로 정규화하지 않습니다.

공개 승인은 `/api/v2/problems`, 회수는 `/api/reclaim`입니다. 요청자·회사는 서버 세션에서 확정합니다.
접수 Idempotency-Key는 같은 키/같은 입력을 재사용하고 다른 입력에는 409를 반환합니다.
분석·실행 내부 API는 `/internal/v2/problems/{id}/...`, 회수는 `/internal/v2/reclaim/...`입니다.

**업무별 완료**

| 상황 | status | 결과·검증 |
|---|---|---|
| 근거 기반 안내 | DONE | result_type=GUIDANCE, verification_ok=null |
| 모의 권한 부여 후 독립 조회 성공 | DONE | result_type=ACCESS_VERIFIED, verification_ok=true |
| 확인된 실행 후 불일치 | FAILED | VERIFICATION_FAILED, verification_ok=false |
| 조회·도구 장애 | FAILED 또는 분석의 MANUAL_REVIEW | 미확인을 false로 바꾸지 않음 |
| 회수 전체 조회·저장·필수 알림 완료 | DONE | result_type·승인 단계·권한 검증 없음 |

안내는 실제 권한 변경이나 오류 해결 완료가 아닙니다. 근거 부족·안내 모델 장애는 수동 검토입니다.
승인·회수 설명 모델 실패는 검증된 템플릿을 사용합니다.

**메시지와 멱등성**

| 작업 | task_type | job_type | 큐 |
|---|---|---|---|
| 승인 분석 | ACCESS_REQUEST | ANALYZE | unlockops.v2.analysis |
| 최종 승인 후 실행 | ACCESS_REQUEST | EXECUTE | unlockops.v2.execution |
| 회수 점검 | RECLAIM_SCAN | RECLAIM_CHECK | unlockops.v2.analysis |

결과는 unlockops.results의 단일 리스너가 업무 종류로 분기합니다. 구 버전·알 수 없는 버전은 거부합니다.
결과 event_id는 중복 방지, job_event_id는 현재 작업 세대 확인에 사용합니다. 과거 결과는 이력만 남기고 적용하지 않습니다.
Worker는 완료 결과를 먼저 체크포인트에 저장하고 발행 확인 뒤 ACK합니다. 재전달은 저장 결과를 재발행하며 도구를 반복 호출하지 않습니다.
실행 키·영수증·예산 잠금과 outbox/inbox를 유지합니다. 승인 대기는 서버가 관리하며 구 interrupt 그래프는 제거했습니다.

**회수 계약**

회수는 current_step=null, total_steps=0, approval_steps=[], verification_ok=null입니다.
고정 snapshot_id/as_of/expected_count와 모든 페이지·중복 여부를 확인해야 scan_complete=true입니다.
정보 부족은 candidate_status=null/review_required=true로 추가 확인 목록에 남깁니다. 개별 미확인은 전체 정상 점검 완료를 막지 않습니다.
전체 조회 실패는 FAILED/SCAN_FAILED, 담당자 미지정 등 필수 알림 실패는 FAILED/NOTIFICATION_FAILED입니다.
검증 가능한 부분 행은 저장할 수 있지만 scan_complete=false이며 알리지 않습니다.
신규 후보·추가 확인 모두 0건일 때만 NO_NEW_CANDIDATES입니다.

PENDING_REVIEW/RETAINED/EXCLUDED는 후보 분류이며 실행 상태와 다릅니다.
비용 UNKNOWN은 null이고 0이 아닙니다. 같은 후보 발생 건과 이미 전달한 알림을 재사용합니다.
인앱 알림은 DB 전달 기록으로 완료하며 읽음·전달·해결은 구분합니다. 점검/Worker 자체는 권한을 회수하지 않습니다.
담당자 확정 모의 회수는 별도 공개 HTTP API의 ReclaimTargetView/ReclaimExecutionState/ReclaimRevokeInput/ReclaimExecutionReceipt/ReclaimExecutionPage/ReclaimExecutionError를 사용합니다.
같은 트랜잭션에서 모의 제공자 부재·INACTIVE 할당·후보 종결을 검증하고 불변 영수증을 저장합니다. 예산 자동 환입은 없습니다.
점검 스냅샷·원본 보고서는 보존하고 현재 overview의 ReclaimTargetView에 RECLAIMED·REVOKED·reclaimed_at·can_revoke를 반영합니다.
POST revoke 본문은 {}이고 이미 처리한 후보는 같은 키 재요청도 409입니다. Worker 점검 모델의 분류/action_taken=NONE은 유지합니다. 권한·재시도·오류 계약은 [전달 문서](../../docs/reclaim-execution-api.md)를 참고하세요.
회수 Worker는 최종 DONE을 보내지 않으며 서버가 결과 저장과 필수 알림을 확인한 후 확정합니다.

**이력과 적용**

프론트 소스·응답 필드, 적용된 Flyway V1~V8, 과거 승인 계획·영수증·정책 revision·회수 스냅샷은 보존합니다.
구 permissions·grant_receipts 등은 과거 데이터로 남지만 현재 쓰기는 access_assignments·access_execution_receipts를 사용합니다.
구 요청·메시지를 새 계약으로 자동 해석하지 않습니다. 과거 대기 업무는 최신 자격·회사·승인 경로를 준비해 재접수합니다.
시연 준비는 `DEMO_SEED_PATH`에서 baseline과 누락된 정책 revision 2·3을 준비하며 이미 적용된 revision은 덮어쓰지 않습니다.
