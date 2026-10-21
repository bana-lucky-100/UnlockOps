# 검증 기록과 재현 절차

## Business MCP → Spring 내부 API 전환 (2026-10-21)

- Business MCP의 SQL Repository와 DB 드라이버 의존성·Compose DB 접속 정보를 제거했습니다.
  `BackendClient`가 자원 검색·접근 조건·실행·검증의 네 Spring API를 호출합니다. 규정 검색·원문 조회는 기존 문서 인덱스를 유지합니다.
- 기존 MCP 도구 입력·성공 응답과 Graph 노드 순서를 유지했습니다. 기존 직원·예산 도구를 위해 접근 조건 API에 직원 단독 조회 및 includeBudget 옵션을 추가했습니다.
  자원·검증 API의 platform은 생략 시 실제 자원에서 확정하고 명시되면 일치 여부를 검사합니다. 자원 없는 platform 단독 조회는 허용하지 않습니다.
- 서비스 토큰 인증, 10초 제한, 리다이렉트 차단, 직원·자원 범위 검사, 엄격한 응답 검증을 적용했습니다.
  HTTP 어댑터는 자동 재시도·전역 조회 캐시·DB fallback을 사용하지 않으며 실행은 기존 키, 검증은 최신 조회를 사용합니다.
- Spring의 code/retryable/reason을 MCP·Agent 오류까지 보존하고 실행/검증 이벤트에도 선택 reason을 기록합니다.
  원문 오류는 POLICY_SOURCE_UNAVAILABLE로 구분하며, 일반 연결·시간 초과·5xx와 혼동하지 않습니다. 내부 응답 원문·URL·토큰은 오류에 노출하지 않습니다.
- `.venv/bin/python -m pytest -q`: **310 passed, 1 skipped**. 실행 중인 전체 스택 테스트 1개만 미실행입니다.
  Spring MockTransport, 실제 MCP ASGI HTTP 및 실제 Graph를 연결해 승인 전 변경 차단 → 승인 후 실행 API → 재조회 → DONE까지 확인했습니다.
  Spring 대신 HTTP 응답을 대체한 경계 검증이며 실제 DB·큐·Spring 네트워크 통합을 대신하지 않습니다.
- Java 운영·테스트 코드 컴파일 통과. 기존과 동일한 임시 JUnit 6.0.3/Mockito javaagent 실행기로 **114개 통과**를 확인했습니다.
  프로젝트 기본 Maven/JUnit 5 실행은 Surefire 캐시 제약이 있어 별도 환경 재확인이 필요합니다.
- `uv --cache-dir .cache/uv lock --offline` 및 `lock --check --offline` 통과. psycopg·psycopg-binary 및 불필요한 tzdata 제거 외 기존 버전 변경은 없습니다.
- 기본/디버그 Compose 설정 검사 및 `git diff --check` 통과. 실제 PostgreSQL·RabbitMQ 전체 스택은 미실행입니다.
- 적용 시 Backend·Business MCP·worker를 함께 재시작합니다. 기존 승인 체크포인트는 같은 도구 이름·입력으로 재개할 수 있으며 실행 영수증·잠금은 Spring에서 확인합니다.

## 내부 최신 권한 반영 검증 API (2026-10-21)

- `POST /internal/access-verifications`를 기존 Controller → Service → Repository 구조 및 내부 토큰 인증 방식으로 추가했습니다.
- 기존 현재 권한 조회를 재사용하며 매 호출 독립된 읽기 전용 트랜잭션에서 확인합니다. State·영수증을 재사용하지 않고 권한·예산·상태를 변경하지 않습니다.
- 역할군 비교는 실행 전 이미 보유한 권한 확인과 공통 `ResourceRolePolicy`를 사용합니다. 기존 실행 정책의 동작도 함께 회귀 검증했습니다.
- 신규 Service 22개·HTTP 5개와 기존 테스트를 대체 실행기로 실행해 **109개 통과, 실패·건너뜀 0개**를 확인했습니다.
- 검증 범위: 같은 서비스의 상위·하위 역할, 권한 없음, 다른 역할군·좌석 구분, Notion 편집 보유 권한, Jira 조회 스킴,
  반복 조회 중 부여·철회 반영, 없는 직원·자원, 플랫폼 불일치, 입력·인증 오류, 조회 오류와 미반영(false) 구분입니다.
- 이전과 같은 캐시된 JUnit Platform/Jupiter 6.0.3 및 Mockito javaagent 임시 실행기를 사용했습니다.
  표준 Maven/JUnit 5 실행은 Surefire 의존성 제약으로 미완료이며 의존성 확보 후 `cd backend && mvn test` 확인이 필요합니다.
- `GrantExecutionIT`에 실제 부여 후 조회 및 영수증이 남아 있어도 철회가 반영되는 테스트 1개를 추가했습니다(통합 테스트 총 5개).
  Docker 환경이 없어 실제 PostgreSQL 통합 실행은 미완료입니다. `mvn verify -Pregression -Dit.test=GrantExecutionIT`로 실행합니다.
- 운영/테스트 코드 컴파일, `docker compose config -q`, `git diff --check` 통과. Business MCP·Agent 연결은 변경하지 않았습니다.

## 내부 승인 계획 실행 API (2026-10-21)

- `POST /internal/problems/{id}/grant`를 추가했습니다. Business MCP와 Agent 호출은 변경하지 않았습니다.
- 승인·계획 해시·최신 승인자·규정 근거·현재 자격을 재검증하며, 요청 행·직원과 자원 advisory lock·좌석 예산 행을 잠급니다.
- 권한 변경·예산 차감·영수증 저장은 하나의 트랜잭션으로 처리합니다. 성공 영수증 재사용·이미 보유한 비좌석 권한·좌석 중복을 구분합니다.
- 신규 실행 Service 10개·Policy 4개·HTTP 5개와 기존 백엔드 단위/HTTP 테스트를 대체 실행기로 실행해 **82개 통과, 실패·건너뜀 0개**를 확인했습니다.
- 이전과 동일한 캐시 JUnit Platform/Jupiter 6.0.3 및 Mockito javaagent 임시 실행기를 사용했습니다.
  표준 Maven/JUnit 5 실행은 Surefire 의존성 누락으로 미완료이며, 의존성을 확보한 환경에서 `cd backend && mvn test` 재확인이 필요합니다.
- PostgreSQL 통합 테스트 `GrantExecutionIT` 4개를 추가했습니다. 동일 요청 재전달, 동일 직원의 중복 요청, 공유 예산 경쟁,
  영수증 장애 시 권한·예산 롤백과 재시도를 실제 트랜잭션으로 검증하도록 구성했습니다.
- Docker 엔진이 꺼져 있고 로컬 임시 PostgreSQL 초기화도 공유 메모리 생성 제한으로 실패하여 통합 테스트는 실행하지 못했습니다.
  Docker 환경에서 `cd backend && mvn verify -Pregression -Dit.test=GrantExecutionIT`를 실행해야 합니다.
- 운영/테스트 코드 컴파일, `docker compose config -q`, `git diff --check` 통과. 기존 업무 DB 변경·서비스 배포는 하지 않았습니다.

## 내부 접근 조건 묶음 조회 API (2026-10-21)

- `POST /internal/access-context`를 기존 Controller → Service → Repository 및 내부 토큰 인증 방식으로 추가했습니다.
- 직원·TF·현재 권한·문서상 상한과 SEAT 대상 예산을 조회합니다. 기존 Business MCP·Agent·승인 정책은 변경하지 않았습니다.
- 회사 권한표의 동일 원문을 읽어 상한과 SHA-256을 반환합니다. Compose에서 원문 data를 Backend에도 읽기 전용으로 마운트합니다.
- 신규 테스트 33개(권한표 21, Service 4, Repository 경계 4, HTTP 4)와 기존 내부 자원 검색 HTTP 5개를 실행해 **38개 통과, 실패·건너뜀 0개**를 확인했습니다.
- 기본 Maven Surefire 3.5.4의 의존성이 로컬 캐시에 없어 표준 `mvn test`는 실행하지 못했습니다.
  임시 실행기에서 캐시된 JUnit Platform/Jupiter 6.0.3과 Mockito javaagent를 사용해 위 테스트를 실행했습니다.
  프로젝트의 기본 JUnit 5.12.2/Maven 실행을 대체한 것으로 주장하지 않으며, 의존성을 확보한 환경에서 `cd backend && mvn test` 재확인이 필요합니다.
- `mvn -o -Dmaven.repo.local=/tmp/unlockops-maven-repository -f backend/pom.xml test-compile -q`,
  `docker compose config -q`, `git diff --check` 통과.
- Repository 테스트는 JdbcTemplate/ResultSet 경계 대체를 사용했습니다. Docker가 꺼져 있어 실제 PostgreSQL의 SQL 실행·트랜잭션 통합 검증은 미실행입니다.

## 내부 대상 자원 검색 API (2026-10-21)

- `POST /internal/resources/resolve`를 Controller → Service → Repository 구조로 추가했습니다.
- 검색·모호성·영문 경계·별칭, 입력 검증, 서비스 토큰 인증·브라우저 세션 차단·명시적 빈 토큰 차단을 위한 테스트 11개를 추가했습니다.
- 내부 API 토큰은 `MCP_TOKEN`과 같은 로컬 기본값 방식입니다. `.env.example`, Compose, Spring 기본값을 맞췄으며 Business MCP 연동은 아직 하지 않았습니다.
- `mvn -o -Dmaven.repo.local=/tmp/unlockops-maven-repository test-compile -q`로 운영 코드·테스트 코드 컴파일을 확인했습니다.
- `docker compose config -q`, `git diff --check` 통과.
- `mvn test`는 기본 로컬 저장소 쓰기 제한 및 Surefire 3.5.4 의존성 누락으로 실행하지 못했습니다.
  쓰기 가능한 임시 저장소와 캐시된 Surefire 3.5.6으로도 테스트 제공자 의존성이 부족했고 외부 저장소 DNS 연결이 실패했습니다.
  테스트 통과를 확인한 상태는 아닙니다. 의존성 접근이 가능한 환경에서 `cd backend` 후 `mvn test`를 실행해야 합니다.
- Docker 엔진이 꺼져 있어 실제 PostgreSQL 통합 실행은 미검증입니다. Business MCP는 변경하지 않았습니다.

## 요청 접수 composable 분리 (이슈 #13)

- 분리 전 기존 키 수명·요청자 홈 회귀 테스트 15개 통과를 확인했습니다.
- 화면 없이 별도 composable 호출 간 같은 접수 키 재사용과 사용자 변경 후 이전 요청의 오류 무시 계약을 먼저 추가했습니다.
  기존 15개는 통과하고 새 2개는 composable 미구현으로 실패하는 것을 확인했습니다.
- `composables/useProblemSubmission.ts`로 인증 사용자 확인·키 관리자 공유·API 헤더·사용자 변경 후 응답 처리를 옮겼습니다.
  뷰는 훅 연결과 호출만 추가하고 폼 검증·전송 표시·상세 이동을 유지합니다. 템플릿·스타일·승인/거절 API 변경은 없습니다.
- `cd frontend && npm test`: 기존 15개 + composable 경계 2개 = **17개 통과**.
  `npm run build`: Vue TypeScript 검사·Vite 빌드 통과. 테스트 의존성 추가 없음.
- 기존과 같은 스크립트 경계 검증이며 브라우저 DOM·실제 backend 전체 스택은 미실행입니다. 백엔드·DB는 변경하지 않았습니다.

## 프론트 화면 분리 후 접수 멱등성 재연결 (이슈 #13)

- main 화면 분리를 병합한 `dd0fcbe`에서 기존 프론트 테스트 11개와 빌드는 통과했지만,
  실제 접수가 `RequesterHome.vue`로 옮겨지면서 helper 호출과 접수 헤더가 누락된 것을 확인했습니다.
- 먼저 요청자 홈의 실제 SFC 스크립트와 API 클라이언트를 실행하는 회귀 테스트 4개를 작성했고,
  접수 키 누락·비로그인 전송·사용자 변경 후 이전 응답으로 이동하는 동작으로 실패하는 것을 확인했습니다.
- `send()`를 공유 `problemSubmissions`에 연결한 뒤 `cd frontend && npm test`: 기존 11개 + 화면 경로 4개 = **15개 통과**.
  재시도·화면 재진입 시 같은 키, 수락 후 이동 실패에도 다음 접수는 새 키, CSRF 유지·중복 클릭·입력 스냅샷·사용자 변경을 검증했습니다.
- `cd frontend && npm run build`: Vue TypeScript 검사·Vite 빌드 통과. 테스트 의존성 추가 없음.
- 라우터·주기 조회·HTTP를 대체한 스크립트 경계 검증이며 실제 브라우저 DOM·실행 중인 backend와의 전체 스택 검증은 아닙니다.
  백엔드·DB·승인/거절 API는 변경하지 않았고 이번 재연결 작업에서 백엔드 테스트를 다시 실행하지 않았습니다.

## HTTP 접수 멱등성 검증 (이슈 #13)

- 기준 main `192e2f4`에서 단위 테스트 19개·기존 회귀 테스트 46개 통과를 확인했습니다.
- 구현 전에 새 순차/8개 동시 접수 테스트가 서로 다른 요청 ID를 반환해 실패하는 것을 확인했습니다.
- 최종 `cd backend && mvn clean verify -Pregression -Dapi.version=1.44`: 단위 19개 + 통합 66개
  (기존 46개·새 접수 19개·서버 재기동 1개) 통과, 실패·오류·건너뜀 0건. Spring Boot JAR 패키징도 완료했습니다.
- 신규 통합 테스트는 일회용 PostgreSQL/RabbitMQ에서 같은 키의 순차/동시 접수, 다른 본문 409,
  사용자 범위·정규화·키 형식·기존 키 없는 요청·인증/CSRF·상태 보존·내부 키 비공개를 검증합니다.
- outbox 저장 실패 시 요청과 키의 롤백, DB lock에서 대기한 후행 요청이 선행 트랜잭션 롤백 후 성공하는 것을 확인했습니다.
- 실제 HTTP 서버를 두 번 기동해 새 쿠키 세션으로 재로그인하고 같은 ID를 반환함을 확인했습니다.
  첫 기동은 Jira 실패 시연 허용, 두 번째는 데모 비활성화 상태로 실행해 기존 수락의 재전송이 새 생성 정책에 막히지 않는 것도 확인했습니다.
- `cd frontend && npm test`: 키 수명·새로고침 복구·사용자/본문 분리·동시 제출·입력 스냅샷·저장소 오류·잘못된 응답의 11개 테스트 통과.
- `cd frontend && npm run build`: Vue TypeScript 검사·Vite 빌드 통과. 테스트 라이브러리 의존성은 추가하지 않았습니다.
- 기존 46개 회귀 시나리오의 검증 내용은 유지했습니다. 통합 테스트의 종료 시 background publisher를 먼저 중지하고
  Spring context를 정리해 Testcontainers 종료 후 DB 재접속·종료 지연이 생기지 않게 했습니다.
- V4는 독립 테스트 DB에서 검증했습니다. 실행 중인 개발 Compose의 DB를 직접 변경하거나 서비스를 재배포하지 않았습니다.
- 이번 자동화 검증은 브라우저 전체 시연, 실제 Python worker/MCP 부수 효과, RabbitMQ 장애 복구 전체 시나리오를 대신하지 않습니다.

## 백엔드 구조 리팩토링 전 기준 (이슈 #9)

- 기준 코드: `9e1d98f` (`main`). 리팩토링 초안은 stash에 보관한 상태에서 테스트를 추가했습니다.
- `backend/mvn verify -Pregression -Dapi.version=1.44`: 기존 단위 테스트 19개와 신규 회귀 테스트 46개 통과, 실패·오류·건너뜀 0건.
- 회귀 테스트는 Testcontainers의 독립 PostgreSQL 16·RabbitMQ 4에서 실제 Flyway V1~V3, Spring HTTP·세션·CSRF, outbox 발행·결과 소비를 실행합니다.
- 검증 범위: 4개 플랫폼 접수·메시지 필드, 공개/담당자 응답, 지정 승인·본인 승인 금지·계획 재검증, 승인/반려, 직급·직무·TF·부서·예산·기존 좌석·Jira 조회 권한, 중복/지연 이벤트, 구 예산 결과 호환, 완료 영수증/검증 필수 및 트랜잭션 롤백, KST 주간 배정 집계.
- Python worker의 결과 envelope를 테스트에서 발행합니다. Agent/MCP가 실제 권한을 부여하는 전체 스택 및 브로커 장애 복구 검증을 대신하지 않습니다.
- 테스트 실행 명령과 Docker API 호환 옵션은 [backend/README.md](../backend/README.md)에 있습니다.

## 백엔드 구조 리팩토링 후 검증 (이슈 #9)

- 원본 기준 회귀 테스트와 설정은 `3373856` 커밋에 보존했습니다. `BackendRegressionIT.java`는 이 커밋 이후 변경하지 않고 동일한 46개 테스트를 적용합니다.
- `backend/mvn clean verify -Pregression -Dapi.version=1.44`: 리팩토링 코드에서 단위 테스트 19개·회귀 테스트 46개 통과, 실패·오류·건너뜀 0건. 실행 가능한 Spring Boot JAR 패키징도 완료했습니다.
- 단위 테스트는 분리된 Repository/Service와 DTO에 맞춰 변경했으며, 실제 HTTP·PostgreSQL·RabbitMQ 동작을 검증하는 회귀 테스트는 그대로 유지했습니다.
- SQL은 Repository에만 있고 운영 코드의 `queryForMap` / `queryForList` / `Map<String, Object>` 전달을 제거했습니다. Flyway V1~V3와 API·worker 계약 문서는 변경하지 않았습니다.
- 리팩토링 전후의 테스트 통과는 위 시나리오에 대한 근거입니다. 실제 Python worker/MCP 실행과 브로커 장애·복구·동시 처리 전체를 검증했다는 의미는 아닙니다.

## 이식 후 확인

- `.venv/bin/python -m pytest -q`: 30 passed, 1 skipped. 전체 스택 옵트인 테스트 1개만 건너뛰었습니다.
- `frontend/npm run build`: Vue TypeScript 검사와 Vite 빌드 통과.
- 기본 Compose와 로컬 디버그 override의 `docker compose config -q` 통과.
- Python wheel 빌드 및 agent·rag·mcp·worker 네 패키지 포함 검사 통과.
- Spring 테스트는 Maven 저장소 접근 제한으로 의존성을 받지 못하여 미완료입니다.
- Docker 엔진이 실행 중이지 않아 이미지 빌드·전체 스택·Flyway 실제 적용은 미검증입니다.
- 유료 LLM·외부 임베딩은 호출하지 않았습니다.

Python 그래프 테스트의 가짜 MCP는 실제 큐·DB 통합 검증을 대신하지 않습니다.
MCP HTTP 검사는 실제 ASGI 앱의 인증·초기화·도구 검색을 확인하며 DB 변경은 하지 않습니다.

## Agent·MCP 경계 개선 검증 (2026-10-20)

- `.venv/bin/python -m pytest -q`: **92 passed, 1 skipped**. 실제 스택 옵트인 테스트만 미실행입니다.
- 범위 밖 해석은 직원·자원 조회 및 승인 카드 생성 전에 수동 검토로 종료합니다. 정상 플랫폼과의 비교 문장은 처리합니다.
- 모의 LLM이 한 응답에 100개 도구 호출을 요청해도 필수 사실·규정 조회가 먼저 완료되고 선택 조회는 10회에서 중단됩니다.
- 필수 조회 오류·누락 필드·잘못된 불리언·예산 응답은 승인 카드 생성으로 이어지지 않습니다.
- MCP 실제 ASGI 요청으로 입력 스키마, 정책 문서 응답·출처 메타데이터, 공통 오류 형식과 retryable 보존을 확인했습니다.
  Business 도구의 DB 호출은 대체했으며 실제 DB 연결·변경 검증은 아닙니다.
- 검증의 일시 오류·미반영만 최대 3회 재조회하고 영구 오류·잘못된 응답은 1회에서 종료합니다.
  검증 실패와 잘못된 실행 응답이 권한 부여 재실행으로 이어지지 않습니다.
- 기존 승인 전 변경 차단, 계획 해시 변경 거부, SQLite 체크포인트 재개 테스트도 통과했습니다.
- Python 모듈 구문 검사와 `git diff --check` 통과. 유료 LLM·실제 외부 서비스는 호출하지 않았습니다.
- Agent와 MCP의 오류 계약이 바뀌므로 함께 재시작·배포합니다. Spring/Vue API 및 DB 스키마 변경은 없습니다.

## 실습 형태로 읽기 쉽게 정리한 코드 검증 (2026-10-20)

- `.venv/bin/python -m pytest -q`: **96 passed, 1 skipped**. 실제 스택 옵트인 테스트는 미실행입니다.
- 노드를 독립 함수로 옮기고 람다 분기를 이름 있는 함수로 바꾼 뒤 기존 시나리오·승인 전 변경 차단·SQLite 체크포인트 재개 검사를 통과했습니다.
- 모델 연결 객체의 재사용과 설정 누락 시 생성 차단을 외부 API 호출 없이 검증했습니다.
- 두 MCP의 실제 도구 목록에서 각 데코레이터의 읽기·변경 힌트 및 입출력 스키마를 확인했습니다.
- State·모델·도구·직급 규칙·공유 계약·Repository·worker 진입점에 짧은 한국어 설명을 추가했습니다.

## 내 승인 현황 집계 수정 검증

- Frontend TypeScript 검사·Vite 빌드 통과.
- ProblemService의 집계 SQL을 PostgreSQL 엔진(PGlite)에서 실행하여 동일 부서 승인자별 분리, 타 부서 요청자 포함, 0건, KST 주간 양끝 경계, 100건 초과, 승인·실패 중복 집계와 부서 프로필 유지를 확인했습니다.
- 같은 검증 데이터에서 기존 부서 기준 SQL의 숫자 불일치를 재현했습니다. 이 검사는 Spring HTTP·실제 운영 DB 통합 검증을 대신하지 않습니다.
- 전체 스택 테스트에 박리더 담당 요청이 윤부장 집계에 포함되지 않는 회귀 검사를 추가했습니다. 테스트 수집은 통과했으며 전체 스택 실행은 미완료입니다.
- Maven 저장소 접근 제한으로 이번 수정의 Spring 테스트 실행은 미완료입니다.

## 로컬 검증 명령

루트에서 실행합니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest -q
docker compose config -q
docker compose -f compose.yaml -f infra/compose.debug.yaml config -q
```

backend에서 `mvn test`, frontend에서 `npm ci`와 `npm run build`를 실행합니다.

## 실제 서비스 통합 확인

1. README의 Docker Compose 명령으로 새 시연 환경을 실행합니다.
2. `kim_dev`로 S1-a 등록. `/api/problems`는 403, `?mine=true`와 본인 상세는 200이어야 합니다.
   요청자 상세·목록에 근거·계획·해시·내부 실행 키가 없어야 하고 events.payload에는 message만 있어야 합니다.
   타인 요청 조회·승인과 `/api/approvals/summary`는 403이어야 합니다.
3. `park_lead`로 로그인. 근거·대상·Write 계획을 확인하고 승인합니다.
4. DONE과 실제 GitHub 팀 멤버십 반영을 확인합니다. `song_ops`는 볼 수 있지만 대신 승인할 수 없어야 합니다.
5. S1-b~d를 각각 등록·승인합니다. 네 건이 독립된 승인 카드로 처리되어야 합니다.
6. S2/S2-b는 직무·직급과 별개로 TF 비구성원 거절이어야 합니다.
7. S3/S8은 질문 화면 없이 MANUAL_REVIEW이어야 합니다.
8. E-005 S4 REJECTED / BUDGET_INSUFFICIENT, E-004 S9 REJECTED, E-001 S6/S7/S10 REJECTED를 확인합니다.
9. S5는 **아직 PAY 권한을 받지 않은 새 시연 데이터**에서 Jira 실패 옵션을 켜고 승인합니다.
   성공한 S1-b를 먼저 실행한 데이터에서는 이미 권한이 있으므로 S5 실패 경로가 발생하지 않습니다.
10. 실행 이력의 execute 시도 1·2·3, 최종 FAILED와 미부여 상태를 확인합니다.
11. 승인 대기에서 agent 컨테이너를 재시작한 뒤 승인하여 동일 체크포인트에서 이어지는지 확인합니다.
12. 브로커 메시지 재전달 상황에서도 같은 실행 키로 권한·예산이 중복 반영되지 않는지 확인합니다.
13. 별도 LLM 모드에서 모델 도구 선택과 실제 MCP 호출 기록을 확보합니다. 데모 모드는 이 증거를 대신하지 못합니다.
14. V3 적용 후 상태 CHECK가 8개이며 기존 ON_HOLD와 INSUFFICIENT_BUDGET 행이 변환됐는지 확인합니다.
    구 결과 메시지·체크포인트 재전달도 새 상태/코드로 처리되어야 합니다. 원본 감사 이력은 유지합니다.
15. 내 승인 현황은 KST 접수 주 시작 직전/직후, 0건, 100건 초과 데이터를 확인합니다. 같은 부서의 TF 리더·부서장이 서로의 요청을 집계하지 않아야 합니다.
    요청자가 다른 부서여도 본인에게 배정되면 포함합니다. 승인 후 실패는 approved와 failed, AI 자동 거절은 rejected에 포함합니다.
    부서명·구성원 수는 승인자 프로필 기준을 유지합니다. song_ops의 전체 목록과 본인 요약은 별도 범위임을 화면에 표시합니다.

새 시연 환경이 이미 실행 중일 때, 위의 인증·지정 승인자·중복 승인·Jira 실패 큐 경로를 자동 확인하는
옵트인 테스트는 다음 명령입니다. 이 테스트는 컨테이너나 DB를 생성하지 않고 실행 중인 환경에 시연 요청을 등록합니다.

```sh
RUN_LIVE_STACK=1 .venv/bin/python -m pytest tests/test_live_stack.py -v
```

동작 로그에는 직원·요청 ID, 도구명, 상태·오류 코드만 남기고 비밀번호·토큰·모델 서비스 원문 오류를 기록하지 않습니다.

## 남은 검증

- Maven 의존성 다운로드가 가능한 환경에서 backend 테스트·패키징.
- Docker 이미지 빌드, V3 마이그레이션과 실제 승인→큐→MCP→권한 부여 흐름.
- 요청자 정보 제한, 내 담당 요청의 KST 집계 SQL, 브라우저 화면 시연.
- SQLite 체크포인트는 단일 worker 전용입니다. worker 확장은 별도 설계가 필요합니다.
