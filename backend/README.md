# Backend

Java 21·Spring Boot 3.5.7·PostgreSQL·RabbitMQ 기반 서버입니다. 현재 다단계 승인과 회수 업무를 한 가지 실행 구조로 제공합니다.

| 패키지 | 책임 |
|---|---|
| `access` | 접수·조회·서버 정책 판정·순차 승인·보류/재개·모의 권한 부여·독립 검증 |
| `reclaim` | 회수 점검·스냅샷·후보/알림·스케줄, 담당자 확정에 따른 모의 권한 회수·검증·영수증 |
| `common/workflow` | 회사·담당 범위 검사, JDBC/JSON 경계, 정책 조항 |
| `messaging/workflow` | 작업 등록과 현재 작업 ID에 연결한 결과 반영 |
| `messaging` | outbox 발행·결과 수신·중복 방지·실패 분류·재시도 |
| `contracts/v2` | 생성된 WorkflowTypes와 엄격한 WorkflowCodec·계획 hash |
| `auth`, `config` | 로그인·시연 로그인·세션·CSRF·내부 서비스 토큰 |

공개 승인 API는 `/api/v2/problems`, 회수 API는 `/api/reclaim`입니다. 프론트의 API·응답 계약은 유지합니다.
필드와 경로는 [HTTP 계약](../contracts/phase2/http.json), 동작은 [공통 계약](../contracts/phase2/README.md)을 참고하세요.

승인은 계획 해시와 버전을 함께 확인하고, 현재 차례의 승인자만 처리합니다. 반려·보류에는 사유가 필요하며 재개는 최신 조건으로 다시 승인받습니다.
권한 부여·예산 차감·영수증은 같은 트랜잭션입니다. 사람의 승인·최신 정책/가격/매핑을 실행 직전 재검증하고, 별도 제공자 상태 조회가 일치해야 DONE입니다.
회수 점검은 후보 선별·알림까지 처리합니다. 별도 세션 API에서 담당자가 확정하면 demo/mock 회사의 SEAT 할당과 모의 제공자 권한을 원자적으로 회수하고 검증된 영수증을 저장합니다. 예산 자동 환입·외부 SaaS·Slack/메일 전송은 포함하지 않습니다. [프론트 전달 API·데이터 계약](../docs/reclaim-execution-api.md)을 참고하세요.

```sh
cd backend
mvn test
mvn verify -Pregression -Dit.test=WorkflowFoundationIT,CompletionMigrationIT,ExistingAccountsMigrationIT
```

일반 시작은 Flyway V1~V10을 적용합니다. V10은 후보 RECLAIMED/reclaimed_at, 후속 action_taken=REVOKED와 불변 회수 영수증을 추가합니다. 이미 적용된 V1~V9와 과거 영수증·스냅샷은 수정하지 않습니다.
Compose 시연 모드에서는 `DEMO_ENABLED=true`, `DEMO_SEED_PATH=/app/data/phase2/seed.sql`로 baseline과 누락된 정책 revision 2·3을 한 트랜잭션에 준비합니다.
이미 설치된 revision은 재작성하지 않습니다. A/B사 시연 계정·로그인 ID는 유지합니다.
이전 `DEMO_PHASE2_SEED_PATH`, `PHASE2_RECLAIM_SCHEDULE_ENABLED`, `PHASE2_RECLAIM_CRON` 환경변수는 설정 호환 별칭으로 받습니다.
현재 설정 이름은 `DEMO_SEED_PATH`, `RECLAIM_SCHEDULE_ENABLED`, `RECLAIM_CRON`입니다.
정기 점검은 설정과 scope.enabled가 모두 켜져야 하며 기본은 꺼져 있습니다.

새 이름은 이전 별칭보다 우선합니다. Compose는 새 이름만 전달하므로 기존 `.env`의 `PHASE2_RECLAIM_*`를 `RECLAIM_*`로 옮겨야 합니다.
로컬 DB 연결은 `DB_URL/USER/PASSWORD`, 브로커는 `RABBIT_HOST/USER/PASSWORD`를 지원합니다. Spring의 브로커 포트는 `SPRING_RABBITMQ_PORT`로 설정합니다.
Spring은 루트 `.env`를 자동으로 읽지 않습니다. 전체 기본값·표준 재정의·Compose 고정값은 [환경변수 안내](../docs/environment.md)를 참고하세요.

구 단일 승인 공개/내부 API와 실행 서비스는 제거했습니다. 모든 로그인 프로필은 현재 화면을 선택하는 workflow_version=2를 반환합니다.
V9는 LEGACY mock 회사의 기존 사용자·자원 ID를 유지하면서 정책 원문·권한 매핑·가격·승인 경로·계정 사실·보유 권한을 현재 모델로 연결합니다. 보유 권한 이관은 예산을 차감하지 않으며 사용 이력은 UNKNOWN입니다. GitHub는 팀 멤버십, Jira는 역할과 Browse 설정을 함께 확인합니다. 높은 기존 역할의 하위 권한도 유효 권한으로 이관합니다.
기존 직무·직급 상한은 권한 매핑의 allowed_job_families/allowed_job_grades로 유지합니다. 부서장 → 기존 문서의 SaaS 담당자(song_ops)로 승인하며 담당자 미지정·중복·본인 승인은 수동 검토입니다. 부서별 좌석 단가·통화가 서로 다르면 임의로 가격을 정하지 않고 가격 확인이 필요합니다.
과거 요청은 같은 목록·상세 API로 조회합니다. 대기 기록은 재분석 필요로 표시하고 재개 시 원본을 감사 이력에 보존한 뒤 현재 계약으로 전환합니다. 이전 계획·승인·실행 키를 폐기하고 새 ANALYZE를 발행합니다. 완료·반려·실패 이력은 다시 실행하지 않습니다.
구 outbox 작업은 자동 발행하지 않으며 현재 `v2.analysis`/`v2.execution` 작업만 발행합니다.
