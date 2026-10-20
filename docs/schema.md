# DB 스키마 요약

실제 DDL은 `backend/src/main/resources/db/migration/V1__schema.sql`, 회사 A사 데이터는 V2에 있습니다.
상태 8개 변경과 본인 요청 목록 인덱스는 V3에 있습니다. V3는 파일만 작성했으며 아직 DB에 적용하지 않았습니다.
새 backend 이미지를 실행하면 Flyway가 V3를 적용하고 기존 ON_HOLD 행을 REJECTED로 변환합니다.

기존 세 테이블을 중심으로 다음 필드와 상태 저장을 추가했습니다.

| 테이블 | 주요 필드·역할 |
|---|---|
| departments | id, name, code, head_id |
| users | 기존 필드 + employee_no, login_id, job_family. 직급 이름은 job_grade로 통일 |
| problems | 기존 필드 + reason_code, decision_source, decided_by, plan, plan_hash, approved_plan_hash, agent_mode, simulate_jira_failure |
| tfs / tf_members | TF 리더와 날짜, 명단의 active 상태 |
| resources | platform, external_id, aliases, access_scope, tf_id, 소유·지정 부서, security_grade |
| permissions | 모의 SaaS의 사용자×자원 단일 현재 역할 |
| github_teams / github_team_members | 저장소×역할 전용 팀과 구성원. 실제 GitHub 부여·재조회 기준 |
| jira_role_permissions | 프로젝트 역할이 실제 Browse 권한을 제공하는지 표현 |
| department_budgets | 부서별 잔여 월 예산·좌석 가격·통화 |
| problem_events | 진행·승인·결과 이벤트 |
| outbox / inbox_events | DB 저장 후 메시지 유실 방지와 결과 중복 수신 제어 |
| grant_receipts | 실행 키별 부여 결과, 문제당 한 번의 실제 반영 |

`problems.resource_id`는 원래 VARCHAR 제안에서 내부 `resources.id` UUID FK로 구체화했습니다.
외부 플랫폼의 ID/이름은 `resources.external_id`와 승인 계획의 `resource_key`에 보존합니다.
`thread_id`는 problems.id와 같은 문자열이며, 체크포인트는 그 ID를 키로 별도 SQLite에 저장합니다.

표의 시드에 포함된 기존 Copilot 좌석 비용은 '이미 차감된 잔여 예산'으로 취급합니다.
시드 로딩 중 다시 차감하지 않으며, 승인 후 새로 부여하는 좌석만 원자적으로 한 번 차감합니다.
