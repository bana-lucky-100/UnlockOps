# Backend

Java 21·Spring Boot 3.5.7·PostgreSQL·RabbitMQ 기반 서버입니다. 현재 다단계 승인과 회수 업무를 한 가지 실행 구조로 제공합니다.

| 패키지 | 책임 |
|---|---|
| `access` | 접수·조회·서버 정책 판정·순차 승인·보류/재개·모의 권한 부여·독립 검증 |
| `reclaim` | 회수 점검 접수·스냅샷·후보 판정·결과 저장·인앱 알림·스케줄 |
| `common/workflow` | 회사·담당 범위 검사, JDBC/JSON 경계, 정책 조항 |
| `messaging/workflow` | 작업 등록과 현재 작업 ID에 연결한 결과 반영 |
| `messaging` | outbox 발행·결과 수신·중복 방지·실패 분류·재시도 |
| `contracts/v2` | 생성된 WorkflowTypes와 엄격한 WorkflowCodec·계획 hash |
| `auth`, `config` | 로그인·시연 로그인·세션·CSRF·내부 서비스 토큰 |

공개 승인 API는 `/api/v2/problems`, 회수 API는 `/api/reclaim`입니다. 프론트의 API·응답 계약은 유지합니다.
필드와 경로는 [HTTP 계약](../contracts/phase2/http.json), 동작은 [공통 계약](../contracts/phase2/README.md)을 참고하세요.

승인은 계획 해시와 버전을 함께 확인하고, 현재 차례의 승인자만 처리합니다. 반려·보류에는 사유가 필요하며 재개는 최신 조건으로 다시 승인받습니다.
권한 부여·예산 차감·영수증은 같은 트랜잭션입니다. 사람의 승인·최신 정책/가격/매핑을 실행 직전 재검증하고, 별도 제공자 상태 조회가 일치해야 DONE입니다.
회수는 후보 선별·알림까지 처리합니다. 권한 말소·예산 환입·외부 Slack/메일 전송은 구현 범위에 포함하지 않습니다.

```sh
cd backend
mvn test
mvn verify -Pregression -Dit.test=WorkflowFoundationIT,CompletionMigrationIT
```

일반 시작은 기존 Flyway V1~V8을 적용합니다. 적용된 migration과 과거 계획·영수증·스냅샷을 변경하지 않습니다.
Compose 시연 모드에서는 `DEMO_ENABLED=true`, `DEMO_SEED_PATH=/app/data/phase2/seed.sql`로 baseline과 누락된 정책 revision 2·3을 한 트랜잭션에 준비합니다.
이미 설치된 revision은 재작성하지 않습니다. A/B사 시연 계정·로그인 ID는 유지합니다.
이전 `DEMO_PHASE2_SEED_PATH`, `PHASE2_RECLAIM_SCHEDULE_ENABLED`, `PHASE2_RECLAIM_CRON` 환경변수는 설정 호환 별칭으로 받습니다.
현재 설정 이름은 `DEMO_SEED_PATH`, `RECLAIM_SCHEDULE_ENABLED`, `RECLAIM_CRON`입니다.
정기 점검은 설정과 scope.enabled가 모두 켜져야 하며 기본은 꺼져 있습니다.

구 단일 승인 공개/내부 API와 실행 서비스는 제거했습니다. 모든 로그인 프로필은 현재 화면을 선택하는 workflow_version=2를 반환합니다.
LEGACY 회사·구 권한·요청 이력은 DB에 보존하지만 새 할당 모델로 자동 복사하거나 구 승인을 새 계획에 재사용하지 않습니다.
시연은 현재 A/B사 계정을 사용합니다. 구 대기 업무를 이어야 하면 최신 회사 정책·담당자·권한 항목을 준비하고 새 요청으로 재접수합니다.
구 outbox 작업은 자동 발행하지 않으며 현재 `v2.analysis`/`v2.execution` 작업만 발행합니다.
