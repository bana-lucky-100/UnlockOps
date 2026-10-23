# 현재 API 명세

로그인·세션·CSRF와 기존 프론트의 공개 API 계약을 유지합니다. 전체 필드와 스키마는 [생성 HTTP 계약](../contracts/phase2/http.json)에 있습니다.
서버가 상태·자격·예산·승인·실행을 확정하고, 에이전트는 해석·근거·설명을 구성합니다. MCP는 서버 호출·정책 검색을 도구로 노출합니다.

| Method / Path | 입력 | 응답·역할 |
|---|---|---|
| POST `/api/auth/login` | loginId, password | 세션과 사용자 프로필 |
| POST `/api/auth/demo-login` | loginId | 시연 모드의 지정 A/B사 계정만 로그인 |
| GET `/api/auth/me` | 세션 | workflow_version=2와 can_reclaim 포함 |
| POST `/api/v2/problems` | schema_version=2, platform, contents, 선택 resource_id/entitlement_id; Idempotency-Key 필수 | 202 AccessView |
| GET `/api/v2/problems` | 세션 | 허용된 요청 AccessView 목록 |
| GET `/api/v2/problems/summaries` | 세션 | workflow·요청자·플랫폼·내용·접수 시각 |
| GET `/api/v2/problems/catalog` | 세션 | 회사별 자원·권한 항목 |
| GET `/api/v2/problems/{id}` | 세션 | AccessView |
| GET `/api/v2/problems/{id}/report` | 세션 | workflow·보고서·계획·근거·승인자·이력 |
| POST `/api/v2/problems/{id}/decisions` | action(APPROVE/REJECT/HOLD), expected_plan_hash, expected_plan_version, reason | 현재 단계 결정. REJECT/HOLD 사유 필수 |
| POST `/api/v2/problems/{id}/resume` | 세션 | 202 최신 조건으로 재분석 |
| GET `/api/reclaim/scopes` | 세션 | 실행·조회 가능한 점검 범위 |
| GET `/api/reclaim/overview` | 세션 | 마지막·진행 중 점검, 후보와 집계 |
| POST `/api/reclaim/runs` | ReclaimStartInput, Idempotency-Key | 202 ReclaimRunView |
| GET `/api/reclaim/runs/{id}` | 세션 | 실행 상태·summary·needs_review |
| GET `/api/reclaim/runs/{id}/items` | 세션 | 미확인 행을 포함한 실행별 판정 |
| GET `/api/reclaim/targets/{id}` | 세션 | 후보 상세 |
| GET `/api/reclaim/notifications` | 세션 | 본인 알림 |
| PATCH `/api/reclaim/notifications/{id}/read` | 세션·CSRF | 최초 read_at 보존 |

변경 요청은 CSRF 검사가 필요합니다. 요청자·회사·허용 담당 범위는 세션과 서버 사실에서 확정합니다.
다른 회사·본인 승인·승인 순서 우회는 403, 현재 상태·계획 해시/버전 충돌은 409, 입력 계약 위반은 400입니다.

MCP용 내부 API는 `/internal/v2/problems/{id}/context|assessment|execute|verify`와 `/internal/v2/reclaim/context|candidates|notification-history`입니다.
INTERNAL_API_TOKEN으로 인증하며 사용자 세션으로 우회할 수 없습니다. execute/verify 입력은 job_event_id·plan_hash·idempotency_key입니다.
서버와 MCP의 책임·도구 목록은 [MCP 계약](contracts/mcp.md)을 참고하세요.

구 단일 승인 `/api/problems`, `/api/approvals/summary`, `/internal/access-context`·`/internal/access-verifications` 등은 제거했습니다.
이전 화면 소스는 프론트 변경 제외 범위에 따라 남지만 사용자 프로필은 현재 화면을 선택합니다. 구 요청 이력은 DB에 보존합니다.
