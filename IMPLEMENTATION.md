# UnlockOps 구현 기록

이 파일은 팀이 구현 내용과 설계 의도를 함께 확인하는 **누적 기록의 기준 파일**입니다.
이후 작업도 새 정리 파일을 만들지 않고 이 파일의 현재 상태와 작업 이력을 갱신합니다.

- 위치: 바탕화면 `UnlockOps/IMPLEMENTATION.md`
- 기준일: 2026-10-23
- 현재 범위: **승인·회수 실행 구조 통합 — 프론트·공개 계약·DB 이력 보존**
- 실제 권한 말소, 외부 SaaS 호출, 실제 가격 적용은 이번 범위가 아닙니다.

최신 통합 구조와 검증 결과는 아래 **승인·회수 실행 구조 통합** 절을 따른다. 초기 단계별 표와 과거 리뷰는 당시 구현 기록이다.

## 단계별 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 공통 계약, DB 확장, mock 정책·가격·사실 데이터 | 구현. 계약 검증 완료, PostgreSQL 통합 실행은 환경 제약으로 미검증 |
| 2 | 서버 승인·보류·회수·알림 업무 API | 구현. 컴파일·핵심 검증 완료, 실제 DB/전체 스택 검증은 남음 |
| 3 | 에이전트·MCP·Worker 연결 | 구현. Python 355건 통과, Java 컴파일 완료. 실제 DB·브로커 전체 실행은 남음 |
| 4 | 프론트 연결 | 구현. 핵심 프론트 테스트·대체 도구 번들/스크립트 검사 완료. 지정 버전 빌드·브라우저·전체 스택 검증은 남음 |
| 5 | 평가셋·전체 시나리오·시연 검증 | 실행기 구현. 오프라인 핵심 검증 통과. Docker 미기동으로 통합 실행 BLOCKED, 브라우저 시연 미검증 |
| 후속 | RAG 근거·가격 문서 갱신, 에이전트 품질 개선 | 베이스라인 완료 후 |

서버 API에 승인 분석·실행과 회수 점검 그래프 및 v2 Worker를 연결했습니다. 자동 흐름 코드는 구현했지만 실제 DB·RabbitMQ·MCP 전체 스택 실행은 아직 검증하지 못했습니다. 4단계에서 승인·회수 화면까지 연결했습니다. 실제 브라우저·전체 스택 검증은 환경 제약으로 남아 있습니다.
5단계에서 원본 평가셋 20건과 보강 시나리오 5건을 실행하는 격리 평가 환경을 연결했습니다. 코드 준비와 실제 시나리오 통과를 구분하며, 현재 전체 스택·브라우저 시연 완료를 선언하지 않습니다.

## 설계 결정과 의도

### 1. v1 실행 흐름과 v2 계약을 명시적으로 구분

기존 6필드 승인 계획·해시, 큐 Job/Result, 체크포인트, API를 그대로 유지했습니다.
v2는 `schema_version=2`, DB에서는 `contract_version=2`로 구분합니다.
이를 통해 아직 단계별 승인을 이해하지 못하는 기존 Worker가 새로운 작업을 잘못 실행하는 것을 막습니다.

기존 v1의 과거 ON_HOLD→REJECTED 호환 처리는 남겨 두었습니다. **v2에서는 ON_HOLD를 그대로 사용**합니다.
신규 계약을 v1 파서로 보내지 않으며, 서버와 Worker는 버전·작업·큐를 확인한 뒤 별도 처리기로 연결합니다.
안내 성공 DONE/GUIDANCE는 이미 구현된 동작이므로 다시 바꾸지 않았습니다.

### 2. 공통 계약의 원본을 하나로 유지

Python `common/phase2.py`에서 JSON Schema, Java DTO, TypeScript 타입을 생성합니다.
Java `Phase2Codec`과 Python validator는 상태·승인·완료 의미를 검증합니다.
공통 정상/실패 JSON 벡터를 양쪽에서 읽어 필드나 해시 해석이 달라지는 문제를 확인합니다.
JSON Schema는 구조 검사, 별도 validator는 필드 간 관계 검사입니다. TS 타입만으로 런타임 응답을 검증했다고 보지 않습니다.

최소 공통 사유/상태 조합은 `reason-status.json`에 생성합니다. 기존 상세 사유 코드를 일괄 삭제하지 않습니다.

### 3. 역할 하나를 덮어쓰는 모델에서 권한 항목별 할당으로 확장

`resources → entitlements → entitlement_revisions → access_assignments`로 나눴습니다.
자원과 부여 가능한 항목, 해당 항목의 외부 의미/매핑, 사용자별 할당은 각각 별개입니다.
같은 사용자에게 여러 권한 항목을 줄 수 있지만 같은 항목의 활성 할당은 하나만 허용합니다.
플랫폼별 권한을 공통 숫자 순위로 비교하지 않습니다.

기존 permissions/GitHub 팀/Jira 스킴은 v1이 계속 소유합니다. 이를 v2 할당으로 복사해 최신 데이터처럼 사용하지 않습니다.
2단계에서는 회사 경계를 기준으로 writer를 분리했습니다. v2는 별도 mock_entitlement_memberships를 변경·조회하고, v1은 LEGACY 회사 자원만 처리합니다.

### 4. 승인 내용의 버전을 해시에 포함

v2 계획은 요청자·회사·자원·권한 항목 외에 권한 매핑/가격/정책/승인 경로 revision과 순서 있는 승인자를 포함합니다.
정책이나 가격이 바뀌어도 기존 승인이 다른 의미의 권한을 허용하지 못하도록 하기 위함입니다.
돈은 decimal 문자열, UUID는 표준 소문자 문자열, 정렬된 JSON의 SHA-256으로 Java/Python 결과를 맞췄습니다.
revision 테이블과 access_plan_versions는 UPDATE/DELETE를 막고 새 revision을 추가하도록 했습니다.

승인 단계에는 계획 버전·해시를 연결합니다. 본인 승인, 다른 회사 승인자, 잘못된 요청자 ID, 동시 WAITING 단계는 DB 제약으로도 차단합니다.
순서대로 승인했는지·현재 자격이 유효한지·최종 승인이 끝났는지는 2단계 Spring 서비스에서 검증합니다.

### 5. 회수 실행과 후보 발생 건을 분리

`reclaim_runs`는 한 번의 점검, `reclaim_targets`는 동일 후보 발생 건, `reclaim_run_items`는 실행별 판정입니다.
같은 후보가 다음 날 다시 조회돼도 기존 episode와 전달 이력을 보존합니다.
후보 상태는 PENDING_REVIEW/RETAINED/EXCLUDED이며 실제 회수 완료 상태는 없습니다.

회수 DONE은 전체 조회·필수 사실·저장·필수 알림 완료를 의미합니다. 권한 검증용 verification_ok는 null입니다.
Worker는 회수 DONE을 만들지 못하고, Spring이 최종 저장·전달을 확인한 뒤 확정합니다.
후보의 review_required, 비용 UNKNOWN, 실패한 알림을 신규 후보 0건으로 바꾸지 않습니다.

### 6. 조직 범위와 스냅샷을 데이터로 표현

company_id와 복합 FK로 직원·부서·자원·할당·후보·알림의 회사 일치를 검사합니다.
operator_assignments는 회사/부서/플랫폼/역할별 실제 담당자 매핑입니다. 기존 APPROVER라고 전사 회수 목록을 볼 수 있는 구조가 아닙니다.
현재 v1 회사는 LEGACY로 연결하고 A/B mock 회사는 별도 ID를 사용해 기존 데이터를 보존했습니다.

reclaim_snapshots/items는 실행 기준 시각과 고정된 조회 집합을 저장하는 기반입니다.
as_of 문자열만 전달한다고 스냅샷이 되지 않으므로 점검 접수 시 서버가 고정된 집합을 만들고 페이지를 제공합니다.
같은 실행이 다른 실행의 snapshot을 참조하거나 다른 회사의 할당을 섞지 못하도록 FK를 연결했습니다.

### 7. mock 정책·가격은 운영 코드와 분리

활성 v1 corpus나 기존 예산을 변경하지 않았습니다.
A/B 임시 정책, 구조화된 가격과 시나리오 조건, SQL seed를 `data/phase2`에 모았습니다.
정책에는 POL-06 제1~5조 및 승인 흐름 제7조의 **합성 기준**이 들어 있습니다.
10개 SaaS의 가격은 SYNTHETIC_CONTRACT이며 USAGE_ESTIMATE는 실제 청구액이 아닙니다.
실제 참고 문서를 확보하면 새 revision으로 교체하고 인용·계획·기대값을 다시 검증합니다.

seed는 Flyway 자동 실행에 넣지 않았습니다. 개발자가 migrated local/demo DB에 명시적으로 적용합니다.
재실행은 같은 ID의 레코드를 덮어쓰지 않습니다. 정책 내용을 바꿀 때 같은 revision에 다시 seed하는 방식은 지원하지 않습니다.
새 시연 계정은 p2_ 접두사이며 암호를 파일에 저장하지 않습니다. 기존 DemoSeed의 해시 생성 경로를 사용합니다.

A사 기본 회수 범위는 R-01 한 건, B사는 X-10 GitHub/Figma 두 건입니다.
다른 TF/유지/이미 알림/퇴사/UNKNOWN은 별도 scope로 분리해 서로 시연 결과에 영향을 주지 않습니다.
모든 새 scope는 enabled=false로 생성합니다. 향후 정기 점검 연결 시 범위 확인 후 켭니다.

## 주요 파일과 팀별 확인 위치

| 파일/디렉터리 | 내용 | 주로 확인할 담당 |
|---|---|---|
| `contracts/phase2/README.md` | 버전·완료·해시·큐·API·MCP 계약 설명 | 전체 |
| `contracts/phase2/schema.json`, `reason-status.json` | 생성된 구조·사유 계약 | 서버·Agent·프론트 |
| `contracts/phase2/http.json` | 구현된 공개·내부 API 계약 | 서버·프론트 |
| `contracts/phase2/examples/` | 정상/실패 사례와 Java/Python 해시 기준 | 전체·평가 |
| `agent/unlockops/common/phase2.py` | v2 계약 원본·의미 검증 | Agent·MCP |
| `backend/.../contracts/v2/` | 생성 DTO·엄격한 JSON 경계·해시 | 서버 |
| `frontend/src/contracts/phase2.ts` | 생성된 v2 타입 | 프론트 |
| `backend/.../db/migration/V6__phase2_foundation.sql` | 신규 스키마, 기존 V1~V5 불변 | 서버 |
| `data/phase2/README.md` | seed 적용·범위·사용 주의 | 전체 |
| `data/phase2/catalog.json`, `seed.sql` | 회사·10개 SaaS·담당자·사실·20개 평가 조건 | 서버·평가 |
| `scripts/generate_phase2_seed.py` | mock 파일 생성 원본 | 서버·정책 |
| `scripts/export_phase2_contracts.py`, `export_phase2_http.py` | 계약 생성/일치 검사 | 전체 |

## API/메시지에서 확정한 선택

- 기존 승인 API에 새 입력을 혼합하지 않고 신규 승인은 `/api/v2/problems`로 준비합니다.
- 회수는 기존 설계의 `/api/reclaim/...` 경로를 유지합니다.
- v2 이벤트는 공통 `result` 봉투를 사용하고 회수 행은 `targets`로 전달합니다. 첨부 초안의 최상위 status/report를 정규화한 부분입니다.
- 공통 작업은 ACCESS_REQUEST/RECLAIM_SCAN, 전송 명령은 ANALYZE/EXECUTE/RECLAIM_CHECK입니다.
- 회수 보고 DTO는 explanation/generation_mode/근거/비용을 사용합니다. 사용자 표시용 문장으로 상태를 분기하지 않습니다.
- 첫 알림 채널은 IN_APP이며 외부 채널용 상태 컬럼만 준비했습니다. 외부 전송은 구현하지 않았습니다.

## DB 적용과 검증

새 backend를 기동하면 Flyway가 V6·V7을 순서대로 적용합니다. 적용된 V1~V5는 수정하지 않았습니다.
이 작업에서 사용자의 실행 중인 DB에 직접 migration/seed를 적용하지 않았습니다.
전체 흐름 완료를 확인하려면 실제 PostgreSQL·RabbitMQ 통합 검증이 필요합니다.

```sh
# Python 기존 회귀 + 신규 공통 계약
.venv/bin/python -m pytest agent/tests mcp/tests -q
# 생성물 일치
.venv/bin/python scripts/export_phase2_contracts.py --check
python3 scripts/export_phase2_http.py --check
# Java 단위 테스트
cd backend
mvn test
# Docker가 켜져 있을 때 V5→최신 migration/실제 제약/seed 재실행 검증
mvn verify -Pregression -Dit.test=Phase2FoundationIT
```

### 2026-10-22 1단계 검증 결과

- 기존 Python 테스트 321개 통과. 신규 계약 테스트 포함 전체 350개 통과.
- Java main/test 소스 컴파일 통과.
- `Phase2ContractTest` 두 테스트 메서드를 직접 실행해 공통 정상·실패 벡터 및 Python/Java 계획 해시 일치 확인.
- TypeScript 생성 타입 단독 strict 검사 통과.
- 생성물 일치 및 diff 공백 검사 확인.
- Maven 정규 test 실행은 환경의 Surefire 의존성 캐시 부족으로 실행하지 못했습니다. 직접 실행한 두 계약 검증을 전체 Java suite 통과로 간주하지 않습니다.
- PostgreSQL 통합 테스트는 Docker daemon 미실행으로 실행하지 못했습니다. 임시 로컬 PostgreSQL도 sandbox 공유 메모리 제한으로 시작되지 않았습니다.
- `Phase2FoundationIT`에 V5 업그레이드, 기존 권한 보존, seed 재실행, 회사/자원 불일치, 중복 할당·실행, revision 불변, 잘못된 완료 상태의 거부를 작성했습니다. **아직 실제 DB에서 통과했다고 주장하지 않습니다.**
- 신규 FK로 인해 기존 통합 테스트의 초기화 TRUNCATE 목록도 갱신했습니다. 기존 업무 로직은 수정하지 않았습니다.

## 2단계 구현과 의도 — 2026-10-22

### 서버 업무 책임을 한곳에서 확정

`backend/.../phase2` 아래에 access/reclaim/messaging/common을 분리했습니다.
`Phase2Store`는 SQL·JSON 경계, `Phase2AccessControl`은 현재 재직 상태·회사·부서·플랫폼 담당 범위를 검증합니다.
핵심 서비스는 Spring 트랜잭션을 사용합니다. MCP나 에이전트가 DB를 직접 수정하는 경로는 없습니다.

| 영역 | 구현 | 의도 |
|---|---|---|
| 접수 | v2 접수·목록·상세·보고서, 필수 Idempotency-Key | 같은 키/같은 입력은 재사용, 다른 입력은 409, 요청자·회사는 세션에서 확정 |
| 정책 판정 | AccessPlanningService | 직무·계정·TF·가격·예산·정책 revision 확인, 문서의 승인 역할을 서버 담당자 매핑으로 해석 |
| 승인 | AccessWorkflowService | 현재 WAITING 단계의 당사자만 결정, 계획 해시 일치 확인, 본인 승인 금지 |
| 보류·반려 | HOLD/REJECT 사유 필수, ON_HOLD/REJECTED 보존 | 사용자에게 사람이 입력한 사유를 전달하고 이후 단계의 실행을 막음 |
| 재개 | 이전 계획/결정 이력 보존, 새 ANALYZE 작업 | 최신 조건으로 처음부터 재승인. 이전 분석 결과가 현재 상태를 덮지 못함 |
| 부여 | AccessExecutionService | 모든 승인 재확인, 예산 행 잠금, 모의 멤버십·할당·예산·영수증 원자 저장 |
| 검증 | 별도 verify API + 결과 반영 시 재조회 | 영수증만으로 성공하지 않고 현재 제공자 상태 일치 후 DONE/ACCESS_VERIFIED |
| 회수 접수 | 수동 POST·09:00 KST 스케줄, 실행 중복 제약 | GET은 조회만 하며 동일 범위의 동시 점검은 409 |
| 스냅샷 | ReclaimSnapshotService | 한 SQL 조회로 사실 집합을 고정하고 정책·규칙·판정을 불변 행으로 저장, 100행 페이지 제공 |
| 회수 판정 | ReclaimPolicy | TF 종료 다음 날 0시·마지막 사용·지급 시각 중 가장 늦은 시각부터 유휴 기간 계산 |
| 결과·알림 | ReclaimResultService | 전체 스냅샷 일치 확인, 후보 발생 건 재사용, IN_APP 알림 중복 방지, 본인 알림 읽음 시각 보존 |

계정 사실 미확인·정책 원문 누락·모호한 담당자는 MANUAL_REVIEW, 예산 부족은 ON_HOLD로 보냅니다.
기존 부여된 권한은 안내로 완료하고 이미 구매한 좌석의 중복 구매는 거절합니다.
직무별 허용 조건은 **합성 정책용 baseline 규칙**이며, 새 자연어 문서가 실행 규칙으로 자동 변환되는 기능은 아직 없습니다.
후속 문서 교체 때 구조화된 매핑·정책 규칙도 함께 검토해야 합니다.

### 버전·큐·결과 연결 보강

- 기존 v1 큐를 그대로 두고 `unlockops.v2.analysis` / `unlockops.v2.execution`을 선언했습니다. 기존 Worker가 새 명령을 오해해 실행하는 것을 막습니다.
- 결과 큐는 `unlockops.results` 하나이며 기존 리스너가 schema_version/task_type으로 분기합니다.
- 결과에 `job_event_id`를 추가했습니다. Job의 event_id를 그대로 돌려주어야 현재 작업 결과로 적용됩니다. 이전 작업 결과는 감사 이력만 남깁니다.
- 결과 event_id는 inbox 중복 제거, job_event_id는 재분석 세대 식별, 실행 idempotency_key는 중복 부여 방지에 각각 사용합니다.
- AccessEvent에 proposed_entitlement_id/policy_evidence, AccessView에 plan_hash/plan_version을 추가하고 Python·Java·TS·예제를 함께 갱신했습니다.
- 서버는 Worker가 제출한 가격·승인 단계·회수 후보 판정을 그대로 저장하지 않습니다. 승인 계획은 다시 만들고 회수 결과는 고정 스냅샷과 비교합니다.

### v1과 v2의 권한 writer 분리

단순히 기존 permissions를 복제하지 않고 v2 모의 제공자 상태를 `mock_entitlement_memberships`에 따로 두었습니다.
새 회사는 v2 API를 사용하고 기존 v1 요청/자원 조회·실행은 LEGACY 회사와 contract_version=1로 제한했습니다.
기존 GitHub 팀/Jira 스킴은 v1이 계속 소유합니다. v2는 해당 mapping revision을 모의 제공자에 저장하여 검증합니다.
실제 GitHub·Jira 등 외부 API adapter는 후속 작업이며 현재 외부 SaaS 변경은 일어나지 않습니다.

### 회수에서 확정한 기준

- 회수 대상은 활성 SEAT 할당이며 scope의 부서·플랫폼·명시된 할당 목록으로 제한합니다.
- 유효 유지 승인, 다른 활성 TF 소속, 최근 사용은 제외/유지 근거로 사용합니다. 사용 이력 UNKNOWN/오래된 관측은 미사용으로 해석하지 않습니다.
- 퇴사 좌석은 별도 EMPLOYEE_LEFT 규칙을 사용합니다.
- 회수 후보의 비용 근거가 없으면 UNKNOWN으로 남기고 실행을 MANUAL_REVIEW로 종료합니다.
- 같은 후보 발생 건의 기존 알림은 재발송하지 않습니다. 새 담당자가 추가된 경우 그 사람의 IN_APP 알림만 추가합니다.
- IN_APP 전달은 알림 행의 DB 저장으로 완료됩니다. 외부 Slack/Email 전송은 없으며 저장 실패는 전체 결과 트랜잭션을 롤백합니다.
- 담당자가 없으면 완료 처리하지 않고 APPROVER_UNAVAILABLE/MANUAL_REVIEW로 남깁니다.
- 범위의 모든 플랫폼 담당 권한이 있는 RECLAIM_REVIEWER/IT_HEAD만 통합 실행을 조회·시작합니다. 개별 담당자는 자기 플랫폼의 후보·알림만 봅니다.
- B사 GitHub/Figma 통합 범위 수동 시연은 `p2_b_it_head`로 접수하고 각 플랫폼 담당자에게 분리된 알림을 저장합니다.
- 실제 권한 회수·좌석 삭제·예산 환입은 하지 않습니다.

### 파일과 실행 설정

| 위치 | 확인할 내용 |
|---|---|
| `backend/.../phase2/access/` | 요청 접수·정책 판정·승인·재개·모의 부여·독립 조회 |
| `backend/.../phase2/reclaim/` | 회수 접수·스냅샷·판정·후보/알림·스케줄 |
| `backend/.../phase2/messaging/` | v2 outbox 명령·inbox 결과와 현재 작업 대조 |
| `backend/.../phase2/common/` | SQL/JSON 경계와 회사·조직·역할 검증 |
| `backend/.../db/migration/V7__phase2_workflows.sql` | 현재 작업/계획 연결, 불변 스냅샷, 모의 제공자와 실행 영수증 |
| `contracts/phase2/http.json`, `README.md` | 공개·내부 API 및 3단계 Worker 연결 순서 |
| `backend/.../Phase2WorkflowTest.java` | 핵심 4건의 짧은 검증 |

`DEMO_ENABLED=true`일 때 수동 회수 점검·모의 권한 부여를 허용합니다.
정기 점검은 `PHASE2_RECLAIM_SCHEDULE_ENABLED=false`가 기본이며 scope.enabled도 기본 false입니다.
3단계 v2 Worker가 연결된 뒤 두 설정을 켜야 정기 실행이 진행됩니다. Compose에도 설정 전달을 추가했습니다.
현재 사용자 DB에 migration/seed를 직접 적용하거나 외부 메시지를 전송하지 않았습니다.

### 2단계 검증 범위

사용자 요청에 따라 테스트를 대량 추가하지 않고 다음 **4건만 신규 추가**했습니다.

1. 미사용 기간은 가장 늦은 사실 시점부터 계산하고 UNKNOWN 사용/비용은 후보 없음으로 바꾸지 않음.
2. 유지/다른 TF 제외와 퇴사자 별도 규칙의 우선순위.
3. 이전 job_event_id의 분석 결과를 이력만 남기고 현재 상태에 적용하지 않음.
4. 기존 실행 영수증 재호출 시 권한·예산을 다시 변경하지 않음.

Java main/test 컴파일과 위 4건, 기존 공통 계약 2건을 직접 호출해 통과했습니다.
변경된 Python 공통 계약 테스트 29건도 통과했습니다.
정규 Maven test는 이전 단계와 같은 Surefire 캐시 제약이 있어 전체 suite를 실행했다고 보지 않습니다.
Docker daemon이 꺼져 있어 실제 PostgreSQL migration·SQL·동시성·롤백·전체 API 통합은 아직 미검증입니다.
새 테스트 컨테이너 suite를 크게 추가하지 않았으며 기존 DB 초기화 목록만 신규 테이블에 맞춰 조정했습니다.

## 3단계 구현과 의도 — 2026-10-22

### 승인 분석·실행·회수 그래프 분리

승인 분석은 `context → interpret → policy → assess → report → finish`로 처리합니다.
서버가 반환한 권한 항목 안에서 대상을 선택하고 회사 정책의 검색 결과와 정확한 원문을 함께 확인합니다.
최종 자격·금액·승인자 판정은 Spring의 assessment를 사용합니다. 에이전트는 설명과 근거를 보완하며 사람의 승인은 서버가 관리합니다.
분석 결과에 계획 해시를 포함하고 서버가 재계산한 해시와 다르면 MANUAL_REVIEW/PLAN_REVIEW_REQUIRED로 전환합니다.
정책·가격이 바뀌었는데 과거 설명을 새 승인 계획에 붙이는 문제를 막기 위한 선택입니다.
검증된 분석 설명은 `diagnosis`에 저장하여 report API의 `analysis_summary`로 제공합니다. 재개 시 이전 설명은 비웁니다.

실행은 별도 `context → execute → verify → finish` 그래프입니다.
분석 체크포인트에 의존하지 않고 서버의 최신 계획·승인 단계·승인 해시·실행 키를 다시 확인합니다.
동일 실행 키로 모의 부여를 요청한 뒤 별도 조회 도구로 반영 여부를 확인합니다.
검증 불일치는 권한을 재부여하지 않고 조회만 재시도하며, 확인된 불일치와 조회 자체 실패를 구분합니다.
서버에서도 실행 영수증과 모의 제공자 상태를 다시 검증합니다.

회수는 `context → policy → scan → history → report → finish`로 처리합니다.
모든 페이지의 run/snapshot/as_of/expected_count를 대조하고 중복 할당·누락·순환 cursor를 검사합니다.
제외·유지·미확인 행도 전체 결과에 보존합니다. 일부 행만 읽고 후보 0건 또는 완료로 보고하지 않습니다.
알림 이력은 조회만 하며 후보 발생 건 재사용·IN_APP 전달·최종 DONE은 Spring이 확정합니다.
회수 그래프에는 쓰기 도구를 허용하지 않았습니다. 실제 말소·환입·외부 메시지 전송은 없습니다.

### MCP와 정책 근거

v2 도구의 입출력 원본은 `agent/unlockops/common/phase2_tools.py`이며 기존 공통 MCP 검증·스키마 노출 경계를 재사용합니다.
Business MCP는 7개 도구를 `/internal/v2/...`에 연결합니다. DB 연결이나 직접 SQL은 추가하지 않았습니다.
Policy MCP에는 `search_workflow_policy`, `read_workflow_policy`를 추가했습니다.
임의 회사나 문서 경로 대신 작업 ID로 서버에서 정책을 찾으며, 회수는 접수 때 고정한 정책을 사용합니다.
따라서 Policy MCP도 `BACKEND_INTERNAL_URL`과 `INTERNAL_API_TOKEN`을 사용하도록 Compose에 연결했습니다.

정책 인덱스는 revision/content/source_hash를 확인한 뒤 조항 단위로 만들고 문서 ID·조항·버전·해시·발췌를 보존합니다.
v2는 로컬 TF-IDF와 정확 조항 읽기를 사용하며 현재 합성 정책의 DB revision을 읽습니다.
불변 문서 인덱스만 최대 32개 재사용하고 직원 사실·가격·실행 결과는 캐시하지 않습니다.
기존 v1 corpus와 실제 참고 문서·가격은 이번 단계에서 교체하지 않았습니다.

LLM은 서버가 확정한 사실과 정책 근거로 설명을 생성하고 별도 내용 검토를 수행합니다.
인용이나 내용 검증에 실패하면 서버 기반 고정 문구를 사용합니다. 상태·비용·후보 판정은 모델이 바꾸지 않습니다.
회수 설명 생성은 호출 예산 내 앞부분 후보에만 적용하고 나머지 행도 기존 설명을 유지합니다. demo 모드는 모델을 호출하지 않습니다.

### Worker 재전달과 실행 한도

- 기존 `analysis/execution`과 신규 `v2.analysis/v2.execution`을 소비합니다. 큐·버전·작업 종류가 다른 메시지는 거부합니다.
- v2 체크포인트 키는 `v2:{task_type}:{work_id}:{job_type}:{event_id}`입니다. 과거 v1, 재분석, 승인 실행이 섞이지 않습니다.
- 완료 결과를 SQLite에 저장한 뒤 results에 발행하고 브로커 확인 후 ACK합니다. 재전달 시 같은 결과와 event_id를 재사용하며 MCP를 다시 호출하지 않습니다.
- 체크포인트 저장 오류와 결과 발행 오류는 재전달 대상으로 남깁니다. 동일 job ID에 다른 입력을 끼워 넣으면 거부합니다.
- 그래프당 도구 호출 한도는 기존 30회, 회수 기본 상한은 500행·결과 2,000,000바이트입니다. 상한 초과는 수동 검토로 보내며 전체 조회 성공으로 처리하지 않습니다.
- SQLite 구성과 기존 single-flight 방식을 유지하여 Worker 한 개를 기준으로 합니다. 다중 Worker 운영은 별도 개선 항목입니다.

### 주요 파일

| 위치 | 역할 |
|---|---|
| `agent/unlockops/access/phase2_graph.py`, `phase2_execution.py`, `phase2_selection.py` | v2 승인 분석·대상 선택·실행 |
| `agent/unlockops/reclaim/graph.py` | 읽기 전용 회수 점검 |
| `agent/unlockops/common/phase2_tools.py`, `phase2_runtime.py`, `phase2_reporting.py` | MCP 계약·작업 범위·오류·설명 생성 |
| `mcp/unlockops_mcp/phase2_backend.py`, `phase2_business.py`, `phase2_policy.py` | 서버 API와 MCP 연결 |
| `rag/unlockops_rag/revisions.py` | 회사별 정책 revision 검색·원문 읽기 |
| `worker/unlockops_worker/phase2.py` | 큐 검증·그래프 분기·체크포인트 결과 재사용 |
| `agent/tests/test_phase2_workflows.py` | 최소 오프라인 흐름 검증 5건 |

### 3단계 검증 범위

사용자 요청대로 신규 테스트는 **5개 함수**에 핵심 경계를 묶었습니다.
승인 대기와 SQLite 재개, 독립 실행/검증 실패 및 중복 실행 방지, 회수 전체 페이지와 중복 행 거부,
큐/버전 분리, HTTP adapter와 정책 해시 불일치를 확인합니다. 기존 MCP 스키마 테스트도 신규 도구 목록을 검사하도록 갱신했습니다.

- Python 기존·신규 테스트 전체 **355건 통과**. 유료 모델·외부 SaaS 호출 없음.
- Java main/test 컴파일 통과. 정규 Maven test는 앞 단계와 같은 의존성 캐시 제약으로 실행하지 못했습니다.
- Docker daemon이 꺼져 있어 실제 PostgreSQL·RabbitMQ·MCP 전체 스택은 미검증입니다. 오프라인 테스트를 전체 통합 검증으로 간주하지 않습니다.
- 사용자 DB에 migration/seed를 직접 적용하거나 기존 실행 중인 서비스를 변경하지 않았습니다.

## 4단계 구현과 의도 — 2026-10-22

### 화면과 사용자 동선

| 경로 | 제공 기능 |
|---|---|
| `/access` | 내 요청·내 승인 차례·허용된 전체 요청 목록, 최근 100건 |
| `/access/new` | 10개 플랫폼 선택, 회사별 자원·권한 선택 또는 요청 내용 분석, 요청 접수 |
| `/access/:id` | 요청 원문·상태·승인 보고서·정책 근거·비용·순서별 승인/반려/보류·재분석·이력 |
| `/reclaim` | 허용된 점검 범위·수동 실행·최근 결과·검토 후보·본인 알림·읽음 처리 |
| `/reclaim/runs/:id` | 전체 판정과 검토 후보/유지/제외/근거 미확인 필터, 조회·알림 진행 상태 |
| `/reclaim/targets/:id` | 후보 상세·정책/사실 근거·예상 비용·개인 읽음 상태 |

기존 디자인 토큰과 AppShell을 재사용하되 `views/phase2`, `components/phase2`, `phase2`로 화면·공통 표시·API를 나눴습니다.
모바일에서는 두 열을 한 열로 접도록 구성했습니다. 실제 브라우저 시각 검증은 아래 제한 때문에 아직 수행하지 못했습니다.
LLM 설명과 정책 인용은 Vue 텍스트 바인딩으로 표시하며 임의 HTML을 실행하지 않습니다.

기존 v1 회사는 기존 화면을 유지하고 새 회사는 `/access`에서 시작합니다.
`/api/auth/me` 및 로그인 응답에 `workflow_version`, `can_reclaim`을 추가했습니다.
회사 설정과 현재 담당 권한을 서버가 계산하며 로그인 ID 접두사로 권한을 추측하지 않습니다.
회수 메뉴는 해당 담당 권한이 있을 때 표시하고 실제 조회·변경 허용 여부는 기존 서버 ACL이 결정합니다.
로그인 화면에는 A/B사 확장 시나리오 계정 선택을 추가했습니다. 계정 선택은 기존 seed 계정을 입력하는 편의 기능입니다.

### 승인 연결의 의도

- 플랫폼 10종과 회사별 자원 목록을 지원합니다. 사용자는 식별 가능한 항목을 고르거나 상세 요청으로 분석을 요청할 수 있습니다.
- 승인 버튼은 현재 WAITING 단계의 approver_id가 로그인 사용자와 같고 계획 해시가 확인될 때만 표시합니다.
- APPROVE/REJECT/HOLD와 `expected_plan_hash`를 전달합니다. 반려·보류 사유는 필수이며 승인 단계별 사유·시각을 요청자도 볼 수 있습니다.
- 409 충돌이나 응답 유실 시 승인 카드를 비우고 서버 상태를 다시 읽습니다. 과거 화면의 결정을 자동 재전송하지 않습니다.
- ON_HOLD/MANUAL_REVIEW는 재분석을 요청할 수 있습니다. 이전 승인을 그대로 이어 붙이지 않고 서버의 새 계획·작업을 받습니다.
- 안내 완료와 권한 반영 확인을 구분하고, 권한 반영 확인은 result_type과 verification_ok를 함께 확인합니다.
- 서버 조회 오류가 있으면 기존 카드의 결정·재개 버튼을 비활성화하고, 401이면 세션 표시를 해제하여 재로그인할 수 있게 합니다.

### 회수 연결의 의도

- 전체 범위를 다룰 수 있는 담당자는 점검을 시작하고 실행별 모든 판정을 봅니다. 개별 플랫폼 담당자는 허용된 후보·본인 알림을 봅니다.
- 점검 DONE은 ‘점검 완료’로 표시합니다. 실제 좌석 삭제·권한 말소·환입 버튼을 추가하지 않았습니다.
- 전체 조회가 확인되기 전의 숫자는 ‘미확정’으로 표시합니다. 결과를 못 읽은 상태와 후보 0건을 구분합니다.
- UNKNOWN 비용은 ‘비용 미확인’, 확인된 0.00은 실제 0.00으로 표시합니다. 금액은 통화별 예상 금액이며 실제 절감 완료로 표현하지 않습니다.
- 미확인 행도 실행 상세에 보존합니다. 전체 결과·유지·제외·검토 후보를 각각 확인할 수 있습니다.
- 읽음은 명시적인 PATCH 요청 성공 후 반영합니다. 후보 해결·알림 전달·권한 회수와 같은 의미로 처리하지 않습니다.
- 실행별 보고서의 read_at은 개인 읽음으로 해석하지 않습니다. 개인 읽음은 해당 사용자의 후보 조회/알림 응답을 사용합니다.

### 서버 조회 보완과 재시도

기존 공통 워크플로 DTO는 유지하고 화면에서 필요한 조회만 보완했습니다.
`GET /api/v2/problems/catalog`는 로그인 회사의 자원·권한 항목을 반환합니다.
`GET /api/v2/problems/summaries`는 기존 목록과 같은 ACL로 workflow·요청자·플랫폼·본문·접수 시각을 반환합니다.
report 응답에는 요청자·승인자 이름, 자원·권한 표시값, 접수 시각을 추가했습니다.
조회 목록의 범위 조건을 공통화하여 별도 화면용 API가 더 넓은 요청을 노출하지 않도록 했습니다.
새 DB migration이나 외부 SaaS 호출은 추가하지 않았습니다.

`phase2/api.ts`는 생성된 타입을 사용하고 상태·버전·업무 ID·현재 승인 단계·계획 해시를 응답 경계에서 확인합니다.
전체 JSON Schema 런타임 검증기를 도입한 것은 아니며, 서버 계약 검증이 최종 기준입니다.
접수와 점검 시작은 사용자·작업 종류·본문별 Idempotency-Key를 유지합니다.
응답을 확인하지 못한 동일 요청은 같은 키로 재시도하고, 수락 확인 후에는 키를 정리합니다.
이미 처리된 작업의 재응답이 RECEIVED가 아닌 상태여도 정상 수락으로 확인합니다.
sessionStorage에는 키와 본문 SHA-256만 저장하고 요청 원문·세션 토큰은 저장하지 않습니다.

상태 조회는 기존 폴링 유틸리티를 재사용합니다. 숨겨진 탭과 중복 조회를 피하며 상세의 완료·반려·실패에서는 중단합니다.
페이지 이동 후 완료된 작업의 finally가 폴링을 다시 시작하지 않도록 unmount 상태 검사도 보완했습니다.

### 4단계 검증 범위와 남은 확인

신규 테스트는 `frontend/tests/phase2.test.mjs`의 **3개**로 제한했습니다.
현재 승인자/계획 경계, 완료·회수·UNKNOWN 표시 의미, 접수 재시도·사용자/작업별 키 분리와 중복 제출을 검증합니다.

- 신규 3건 및 실행 가능한 기존 16건, 총 **19건 통과**.
- Java main/test 컴파일 통과. API 계약 생성물 일치 및 diff 공백 검사 통과.
- 잠금 파일의 Vue 3.5.44 / vue-tsc 3.3.13 등 일부 패키지가 로컬 캐시에 없고 registry DNS 접근이 실패하여 정규 `npm ci`/`npm run build`는 완료하지 못했습니다.
- 별도 임시 디렉터리에 캐시된 Vue 3.5.41 / vue-router 4.6.4 / Vite 8.2.2 / plugin-vue 6.0.8을 설치하여 번들 생성에 성공했습니다. Vue SFC script를 추출해 로컬 TypeScript 7.0.2 strict 검사도 통과했습니다. **지정 버전 vue-tsc의 템플릿 포함 타입 검사와 동일한 검증은 아닙니다.**
- 기존 `requesterHome.test.mjs` 6건은 로컬 TypeScript 7에 기존 transpileModule API가 없어 실행 과정에서 오류가 났습니다. 25건 전체 통과라고 기록하지 않습니다. 프로젝트 package.json/lockfile의 버전은 바꾸지 않았습니다.
- 브라우저 점검을 위해 로컬 서버를 실행하려 했으나 sandbox가 listen을 EPERM으로 차단했습니다. 실제 브라우저 클릭·레이아웃·전체 API 연동 검증은 수행하지 못했습니다.
- 실제 PostgreSQL·RabbitMQ 전체 스택 검증은 앞 단계와 마찬가지로 남아 있습니다. 사용자 DB·기동 서비스·seed는 변경하지 않았습니다.

## 5단계 — 평가 실행기와 시연 기준

### 변경 내용과 의도

| 파일 | 역할·의도 |
|---|---|
| `scripts/evaluate_phase2.py` | 표준 라이브러리만 사용하는 실행 명령. 준비/실행 분리, Docker 사전 확인, 설치·DB 검증·결과 저장·정리 |
| `scripts/phase2/fixtures.py` | 원본 20건의 overrides 적용과 추가 5건. 실행별·시나리오별 회사/UUID/계정 격리, 실행일 기준 날짜 보정 |
| `scripts/phase2/run_suite.py` | 실제 세션/CSRF를 사용해 프론트 nginx→Spring API→RabbitMQ→Worker→MCP 흐름을 실행하고 상태·근거·부수 효과 비교 |
| `infra/compose.phase2-eval.yaml` | 평가 전용 PostgreSQL/RabbitMQ/서버/MCP/에이전트/프론트/평가 컨테이너. 공개 포트 없음 |
| `frontend/Dockerfile` | 평가 빌드에서만 RUN_TESTS=true로 기존 프론트 테스트 실행. npm ci 및 타입 검사·번들은 기존 잠금 파일 기준 |
| `.github/workflows/phase2-evaluation.yml` | 수동 실행 전용 smoke/full 평가. 결과를 GitHub job summary에 표시. 이번 작업에서 원격 실행하지 않음 |
| `scripts/phase2/test_evaluation.py` | 평가 준비 자체의 핵심 오프라인 검증 3건. 별도 대규모 단위 테스트 추가 없음 |

서버/에이전트가 통과 결과를 미리 반환하도록 바꾸지 않았습니다. 평가 실행기는 실제 비동기 결과를 기다립니다.
성공 경로에서 지정 승인자 계정으로 차례대로 승인하고, 반려 시나리오는 해당 단계에서 직접 반려합니다.
mock·demo 모드로만 동작하며 유료 LLM·외부 SaaS·외부 알림을 사용하지 않습니다.

### 데이터 격리와 조건 적용

- UUID 실행 ID로 새 Compose 프로젝트를 만들고 DB·큐·체크포인트 볼륨도 독립시킵니다. 기존 compose/.env/DB 접속을 인자로 받지 않습니다.
- 시나리오마다 A/B 회사와 사실 데이터를 복제합니다. 앞 시나리오의 예산 차감·승인·알림이 다음 시나리오를 바꾸지 않습니다.
- SQL은 DB 이름이 `phase2_eval`일 때만 적용됩니다. 복사 계정은 격리 서버의 demo 비밀번호 해시를 DB 내부에서 복사하며 보고서로 내보내지 않습니다.
- 회수 기준일·TF 종료·마지막 사용·유지 승인 날짜는 실행일과 동일한 간격으로 이동합니다. 사용 관측 시각은 복사 데이터에만 현재 시각을 기록합니다. 원본 seed와 정책 본문/hash는 그대로 유지합니다.
- B-02는 Admin 요청에 Read entitlement를 미리 넣지 않고 에이전트가 최소 권한을 선택하도록 합니다. B-04는 Slack 자원의 TF 범위를 먼저 지정한 뒤 구성원 조건을 해제합니다.
- B-03은 기존 불변 정책을 삭제하지 않고 읽을 조항이 없는 새 revision을 추가합니다. X-COST는 같은 권한에 유효 가격 근거가 둘인 상황을 만들어 비용을 확정할 수 없게 합니다.
- `execution_ready=true`는 실행기가 준비됐다는 뜻입니다. 원본 `validation_status=NOT_RUN`과 실행별 결과를 분리해 미실행을 통과로 표시하지 않습니다.

### 검증 범위

| 묶음 | 확인 내용 |
|---|---|
| E-01~E-05 | A사 2단계 승인·독립 실행 검증, 예산 부족 보류, 기존 권한 안내, 1/2단계 반려. E-01에서 담당자 보류→재분석→새 승인 계획까지 확인 |
| P-01~P-06 | 추가 SaaS 6종의 실제 계획·가격·승인 경로·모의 실행. B사 Figma는 전담 승인자 포함 |
| B-01~B-05 | 직무 불일치, Admin→Read, 정책 근거 없음, TF 비구성원, 지원 범위 밖 요청 |
| R-01~R-04 | 신규 후보·다른 활성 TF 제외·유지 승인·기존 전달 알림. 스냅샷 전체 할당 결과와 사유 비교 |
| X-10 | GitHub/Figma 담당자 분리, 허용 플랫폼 후보만 조회, 전체 범위 무단 조회 거절 |
| X-UNKNOWN / X-COST | 사용 미조회와 비용 미확정을 각각 검증. MANUAL_REVIEW, 확정 판정 없음, UNKNOWN 금액이 null인지 확인 |
| X-4STEP / X-11 | B사 100 USD 이상 4단계 승인 / 퇴사자 좌석 후보 |

공통으로 접수 키 재전송, 승인 순서, 보고서 근거·금액을 검사합니다. E-01에서는 다른 본문에 같은 키 사용(409), 잘못된 계획 hash(409), 본인/미래 단계 승인(403), 다른 회사 조회(403), 미로그인 조회(401)를 확인합니다.
완료 후 실행을 같은 실행 키로 재호출해 영수증이 같고, DB 예산이 한 번만 차감됐는지 검사합니다. 안내·반려·보류는 실행 영수증이 없어야 합니다.
회수는 동일 범위 재점검 시 episode와 알림이 추가되지 않는지, 읽음을 재전송해도 read_at이 유지되는지 검사합니다. DB의 원래 할당이 ACTIVE이며 예산 환입이 없는지도 비교합니다.
신규 DB의 V1~V7 적용과 LEGACY 요청·사용자·예산 불변을 검사합니다. **기존 V5 운영 데이터의 업그레이드 검증과 같은 의미는 아닙니다.** 기존 데이터 복제본의 업그레이드는 별도 확인이 필요합니다.

### 실행 방법과 결과 해석

```sh
# 데이터/기대값 준비만 수행: 기본 동작이며 서비스 시작 없음
python3 scripts/evaluate_phase2.py --plan --suite full

# Docker가 실행된 환경에서 핵심 8건 또는 전체 25건
python3 scripts/evaluate_phase2.py --run --suite smoke
python3 scripts/evaluate_phase2.py --run --suite full

# 실패 상태를 조사할 때만 평가 전용 컨테이너·볼륨 유지
python3 scripts/evaluate_phase2.py --run --suite smoke --keep

# 평가 준비의 핵심 오프라인 확인
.venv/bin/python -O scripts/phase2/test_evaluation.py
```

`test-results/phase2/<run_id>/`에 bundle.json, fixtures.sql, report.json과 실행 시 runtime.log가 생성됩니다. Git 추적에서는 제외합니다.
보고서는 PASS/FAIL/ERROR/TIMEOUT/NOT_RUN을 사례별로 집계합니다. 환경·설치 문제는 전체 BLOCKED로 기록하고 0이 아닌 종료 코드를 반환합니다.
실행이 실패해도 기본적으로 이 실행에서 만든 프로젝트만 `down --volumes`로 정리합니다. `--keep` 또는 정리 실패 시 보고서의 project 이름을 확인해 같은 compose 파일과 bundle 경로로 정리합니다.
프론트 지정 버전 설치·테스트·build는 평가 스택 빌드에 포함됩니다. 프론트 HTML 응답 확인은 브라우저 상호작용 검증이 아니므로 `browser_interaction=NOT_RUN`을 유지합니다.

### 실제 브라우저 시연 체크리스트 — 아직 미실행

평가 스택은 포트를 공개하지 않습니다. 브라우저 시연은 기존 로컬 demo 환경의 `/access` 및 `/reclaim` 화면에서 별도로 수행합니다. 아래는 완료 기록이 아니라 확인할 항목입니다.

1. A사 requester의 GitHub 신청 → head → operator 승인 → 요청자 화면의 ‘권한 반영 확인’. 순서 밖 계정에 승인 버튼이 없어야 합니다.
2. B사 Figma의 team_lead → head → figma_operator 승인과, 예산을 확보한 Snowflake의 IT 총괄 추가 단계를 확인합니다.
3. 담당자 보류·반려 사유 표시, 재개 후 승인 초기화, 두 탭에서 변경된 계획을 승인할 때 충돌 후 새로 조회하는 동작을 확인합니다.
4. 회수 후보·제외·유지·미확인 행을 함께 확인합니다. 비용 UNKNOWN은 0원으로 표시되지 않고, 점검 DONE은 실제 권한 회수 완료로 표시되지 않아야 합니다.
5. 담당자별 알림·읽음·플랫폼 범위와 새로고침 후 읽음 유지, 재점검 알림 중복 여부를 확인합니다.
6. 세션 쿠키 만료 후 재로그인, 모바일 폭에서 승인 카드·정책 근거·알림 표시, 응답 유실 뒤 동일 접수 재시도를 확인합니다.

### 5단계 검증 결과와 남은 조건

- 새 오프라인 검증 **3건 통과**. Python 최적화(-O)에서도 실패 검사가 제거되지 않는지 확인했습니다.
- 기존 Phase 2 계약·그래프 테스트 **34건 통과**. 기존 catalog 테스트는 ‘실행기 준비’와 ‘아직 미실행’ 메타데이터를 구분하도록 갱신했습니다.
- full 25건의 입력·격리 SQL 준비 성공. Compose 설정 해석, Python 문법, 공통 계약/HTTP 생성물 일치 확인 완료.
- Docker daemon 소켓이 없어 실제 실행 사전 확인에서 **BLOCKED**. 시나리오를 PASS로 기록하지 않았으며 기존 DB·서비스를 변경하지 않았습니다.
- 지정 버전 프론트 설치·전체 컨테이너 실행·실제 SQL 적용·브라우저 상호작용·기존 V5 데이터 업그레이드는 이번 환경에서 미검증입니다.

## 1~5단계 전체 코드 리뷰 — 2026-10-22

계약·migration·서버 승인/실행/회수·Worker·MCP·RAG·프론트·평가 실행기를 읽고 경계 조건을 확인했습니다.
리뷰 시점에는 업무 코드 수정 없이 아래 5건을 기록했습니다. 이후 CR-01·CR-02 수정 완료, CR-03~05는 미해결입니다.
P1은 우선 수정할 승인 정확성 문제, P2는 후속 수정할 조회·상태 표시 문제입니다.

### CR-01 · P1 · 명시한 역할을 찾지 못하면 다른 권한을 선택함 — 수정 완료

- 위치: `agent/unlockops/access/phase2_selection.py` 37행, 45행.
- `requested_role`과 일치하는 항목이 없을 때 options를 그대로 둡니다. 남은 항목이 하나면 다른 역할이어도 그 ID를 반환합니다.
- 실제 선택 함수를 호출해 `Figma Viewer 권한을 신청합니다.` → `EDITOR_SEAT`, `Jira Viewer 권한을 신청합니다.` → `DEVELOPER`를 재현했습니다.
- 요청한 조회 권한보다 강한 편집 권한이나 유료 좌석의 승인안을 만들 수 있습니다. 사람 승인 절차가 생략되는 문제는 아니지만, 검토 대상 계획 자체가 요청과 달라집니다.
- 수정 방향: 플랫폼별로 허용한 역할 별칭만 명시적으로 매핑하고, 명시 역할이 해소되지 않으면 OUT_OF_SCOPE/MANUAL_REVIEW로 중단합니다. 후보가 하나라는 이유로 역할 불일치를 허용하지 않습니다.

### CR-02 · P1 · 재분석 전 승인 요청이 새 회차에 적용됨 — 수정 완료

- 위치: `backend/src/main/java/com/unlockops/phase2/access/AccessWorkflowService.java` 138행, `agent/unlockops/common/phase2.py` 110행의 계획 계약.
- 승인 API는 expected_plan_hash만 비교합니다. plan_version과 분석 작업 ID는 해시에 포함되지 않아 조건이 같은 재분석은 이전과 동일한 해시를 만듭니다.
- 재현 조건: v1 승인 화면을 유지 → 다른 화면에서 보류·재개 → 동일 조건으로 v2 계획 생성 → 이전 화면에서 승인. 동일 승인자가 현재 순서이면 v2를 승인합니다.
- 계획 해시 동일성을 Python에서 확인했고, 실제 Java decide 메서드에 DB/ACL mock을 연결해 이전 해시의 요청이 plan_version=2 승인 UPDATE를 수행하는 것도 확인했습니다. 실제 DB 동시 실행 시험은 아닙니다.
- 수정 방향: 결정 입력에 expected_plan_version 또는 별도 승인 회차 토큰을 추가하고 현재 회차와 함께 비교합니다. 생성 계약·프론트·평가 실행기도 같이 갱신해야 합니다.

### CR-03 · P2 · 새 회수 결과가 미확인이어도 후보 상세는 과거 확정 결과를 표시함

- 위치: `backend/src/main/java/com/unlockops/phase2/reclaim/ReclaimResultService.java` 49행, `ReclaimWorkflowService.java` 87행 및 109행.
- 기존 PENDING_REVIEW 후보에 대해 새 점검이 사용 이력/가격 미확인으로 바뀌면 review_required 분기는 기존 target을 조회하지 않고 target_id=null로 결과를 저장합니다. 기존 열린 target은 남습니다.
- 후보 목록·상세는 target_id로만 최근 report를 찾으므로 새 미확인 행을 건너뛰고 이전의 확정 후보와 금액을 표시합니다. 전체 실행 조회 권한이 없는 플랫폼 담당자는 새 미확인 상태를 후보 상세에서 확인할 수 없습니다.
- 실제 Java 결과 처리 메서드에 mock 저장소를 연결해 UNKNOWN 결과에서 기존 target 조회가 없고 run item의 target_id가 null로 전달되는 것을 확인했습니다. 조회 SQL과 연결해 결과를 추적했습니다.
- 수정 방향: 기존 episode와 새 미확인 결과의 연결을 유지하거나 assignment 기준으로 최신 판정을 조회해야 합니다. UNKNOWN 때문에 과거 확정 판정으로 되돌아가면 안 됩니다.

### CR-04 · P2 · 상태와 승인 단계를 다른 시점에 읽어 정상 조회가 400으로 끝남

- 위치: `backend/src/main/java/com/unlockops/phase2/access/AccessWorkflowService.java` 68행.
- 요청 행을 읽은 후 별도 쿼리로 approval_steps를 읽습니다. 기본 READ_COMMITTED에서 두 SELECT 사이에 최종 승인/반려/보류가 커밋되면 이전 WAITING_APPROVAL 상태와 새 승인 단계가 결합됩니다.
- 실제 view 메서드에 이전 WAITING_APPROVAL 행과 전부 APPROVED가 된 단계를 전달하면 `Current step required` 예외가 발생합니다. 공통 예외 처리기가 이를 HTTP 400으로 반환하므로 정상 폴링에 ‘입력 형식 확인’ 오류가 나타납니다. 목록에서는 한 건의 불일치로 전체 목록 조회가 실패할 수 있습니다.
- 수정 방향: 상태와 단계를 단일 SQL로 읽거나, 해당 읽기 트랜잭션 전체를 동일 스냅샷으로 구성합니다. 응답 계약 검사를 느슨하게 하는 방식으로 해결하지 않습니다.

### CR-05 · P2 · 오래된 미처리 승인이 ‘내 승인 차례’에서 누락됨

- 위치: `backend/src/main/java/com/unlockops/phase2/access/AccessWorkflowService.java` 65행, `frontend/src/views/phase2/AccessList.vue` 13행.
- 서버가 상태와 관계없이 최근 100건을 자른 뒤 프론트에서 ‘내 승인 차례’를 필터링합니다. 오래된 미처리 요청보다 새 조회 가능 요청이 100건 있으면 미처리 요청을 가져오지 않습니다.
- 화면에는 추가 페이지나 오래된 대기 요청을 다시 조회하는 경로가 없어, 대기 업무가 존재해도 ‘해당하는 요청이 없습니다’로 표시될 수 있습니다. SQL 제한과 프론트 필터 순서로 확인한 문제입니다.
- 수정 방향: 내 요청/현재 승인 대기 필터를 서버에 전달하고 필터 적용 후 페이지를 나누거나, 승인 대기 목록을 별도 조회합니다.

### 리뷰 중 검증 및 평가 보강 대상

- Python agent/MCP 기존 검사 355건 통과, 평가 준비 검사 3건 통과, 프론트 Phase 2 검사 3건 통과.
- Java main/test 오프라인 컴파일 통과, 공통 계약·HTTP 생성물 일치 확인.
- 별도 임시 재현 코드로 권한 선택, 이전 회차 승인 수락, 미확인 결과의 target 연결 누락, 혼합 시점 조회의 계약 오류를 확인했습니다. 저장소에 추가 테스트를 대량 작성하지 않았습니다.
- 기존 5단계 평가는 대부분 권한 ID를 직접 전달하고, 잘못된 임의 해시와 처음부터 UNKNOWN인 새 회사만 검사합니다. 따라서 위 역할 불일치, 실제 이전 회차 해시 재사용, 기존 후보→UNKNOWN 변화가 검사에서 빠져 있습니다. 해당 재현 조건을 작은 회귀 사례로 보강해야 합니다.
- Docker daemon은 여전히 미기동입니다. 실제 PostgreSQL·RabbitMQ 전체 통합, 브라우저 상호작용, 지정 버전 프론트 전체 빌드는 이번 리뷰에서 검증하지 못했습니다.

## 리뷰 후 개선 — CR-01·CR-02 (2026-10-22)

### CR-01: 요청한 역할과 실제 권한 후보를 일치시킴

- `agent/unlockops/access/phase2_selection.py`: 명시된 역할 코드와 일치하지 않는 후보를 제거합니다. 일치하는 후보가 없으면 OUT_OF_SCOPE 오류로 분석을 중단하고 기존 그래프가 MANUAL_REVIEW로 전환합니다. 후보가 하나뿐이어도 다른 권한으로 대체하지 않으며 LLM 선택에도 넘기지 않습니다.
- 의도: Viewer 요청이 EDITOR_SEAT·DEVELOPER 권한의 승인 계획으로 바뀌는 것을 방지합니다. 지원하지 않는 역할 별칭은 임의로 추측하지 않고 수동 검토합니다.
- 기존의 명시 entitlement ID 처리, 역할 코드 대소문자 무시, Admin 계열 요청의 Read 최소 권한 제안은 유지합니다.

### CR-02: 사용자 결정을 조회한 승인 회차에 고정함

- `ApprovalDecisionInput`에 1 이상의 필수 정수 `expected_plan_version`을 추가하고 JSON Schema·Java·TypeScript 생성물을 갱신했습니다. 프론트는 조회 당시 해시와 버전을 함께 전송하며, 유효한 버전 없는 승인 대기 응답은 허용하지 않습니다.
- 서버 `decide`는 기존 요청 행 잠금 안에서 현재 `active_plan_version`과 입력 버전을 먼저 비교합니다. 그 뒤 해시·승인자·정책 조건을 검사합니다. 승인·반려·보류 모두 같은 검증을 거치므로 이전 회차 요청은 상태를 변경하기 전에 409로 거절됩니다.
- 의도: 해시는 계획 내용의 동일성을, 버전은 검토 회차의 동일성을 보장합니다. 보류·재개 후 내용이 같아도 새 회차의 결정은 새 화면에서 내려야 합니다. 해시 형식과 DB 구조를 변경할 필요는 없습니다.
- 호환성: v2 결정 API는 새 필드가 필수이므로 서버와 프론트·외부 v2 호출자를 함께 갱신해야 합니다. 버전 누락·0 이하는 입력 오류(400), 현재 회차·해시 불일치는 충돌(409)입니다. v1 계약은 변경하지 않았습니다.
- 평가 실행기는 새 필드를 전달하고 E-01에 동일 해시의 이전 회차 승인·반려·보류 거절 및 현재 상태 유지 확인을 추가했습니다.

### 변경 검증

- Python Phase 2 계약·그래프 검사 **39건 통과**. Figma·Jira Viewer의 수동 검토 및 서버 권한 평가/실행 미호출을 확인했습니다. 같은 검사에서 정상 역할 및 Admin→Read 동작도 확인했습니다.
- Java 오프라인 main/test 컴파일 통과. 직접 실행한 워크플로 검사 5건·공통 계약 검사 2건 통과. 새 검사는 동일 해시의 이전 버전 결정 3종이 409로 끝나고 DB 변경이 없으며, 현재 버전의 승인은 진행되는지 확인합니다.
- 프론트 Phase 2 검사 **3건**, 평가 준비 검사 **3건** 통과. 공통 계약·HTTP 생성물 일치 확인 완료. 공통 계약 벡터로 정상 결정·버전 누락·0 및 기존 보류 사유 검증을 Python/Java에서 확인했습니다.
- 실제 PostgreSQL·브로커를 사용하는 E-01 통합 평가와 브라우저 상호작용은 이번 수정에서 실행하지 않았습니다. 지정 버전 프론트 전체 빌드도 미검증입니다.

## 수신 RAG 문서 반영 — 2026-10-23

### 변경 내용과 의도

- 제공받은 `policy_corpus.md`를 `data/phase2/policies/policy_corpus.md`에 원문 그대로 보관했습니다. 총 28개 문서(POL-01~14 및 공식 요약 14개), 107개 조항/요약 청크입니다. 원문 SHA-256은 `5e1a78226662b90b9dfb10865bfde4d67a1eb6274b654bf25308c3bf594c1912`입니다.
- `rag/unlockops_rag/corpus.py`가 메타데이터 표의 문서 ID·플랫폼·버전/확인일을 읽습니다. 규정 조항과 공식 요약의 중첩 제목을 구분해, 서로 다른 문서의 `핵심 요약`이 동일한 근거 키로 덮이는 것을 방지했습니다.
- `scripts/import_phase2_policy.py`는 A/B 회사별 승인 경로·시연 가격 해석을 결합한 정책 묶음 revision 2와 opt-in `apply.sql`을 생성합니다. DB의 회사 정책 ID/버전/전체 해시는 유지하고, 원문 문서 ID·버전·조항은 근거 article에서 확인합니다.
- `RevisionIndex`와 Policy MCP는 승인 요청의 플랫폼을 서버 context에서 받아 해당 플랫폼+COMMON만 검색·정확 조회합니다. 기존 원문 해시 검증, 회사/버전별 캐시와 회수 스냅샷 정책 고정은 유지합니다. 임베딩 모델은 필요하지 않습니다.
- 정책만 교체하면 서버의 연결 버전 검사에서 차단됩니다. 따라서 SQL은 정책·가격·승인 경로·회수 규칙 revision 2를 하나의 트랜잭션에 추가합니다. 기존 revision 1과 과거 계획/스냅샷은 수정하지 않습니다. 같은 적용은 중복 생성하지 않고, 다른 내용의 동일 버전이나 이후 버전은 거절하도록 구성했습니다.
- v1은 단일 승인·Admin 거절 등 규칙이 다르므로 기존 `data/policy_corpus.md`를 보존합니다. 기존 baseline seed와 smoke/full 평가는 revision 1을 유지하고 수신 정책 반영은 별도 SQL로 적용합니다.

### 확인된 차이 및 한계

- Figma 원문 예시는 월 16달러, 기존 mock 계약은 월 15.00 USD입니다. 이번에는 검색 문서를 반영했으며 구조화된 가격은 유지합니다. 실제 가격·계약 변경은 별도 revision 작업이 필요합니다. 원문의 공식 요약과 링크는 외부 웹으로 재검증하지 않았습니다.
- Tableau 허용 직무, Databricks 실행 주체의 데이터 접근, Notion 기밀 편집의 추가 승인, Figma View 카탈로그, Admin→Read 제안의 목적 검증에는 문서와 현재 구현 차이가 남습니다. 정책 문장이 자동으로 실행 규칙으로 바뀌지는 않습니다. 구체적인 차이는 `data/phase2/policies/README.md`에 기록했습니다.
- 실제 서비스 반영은 V7·baseline seed 적용 후 `data/phase2/policies/apply.sql`을 실행해야 합니다. 이번 환경에서는 Docker 소켓 접근이 거절됐고, 임시 PostgreSQL도 공유 메모리 생성 권한 제한으로 시작하지 못해 실행 중 DB 적용은 하지 못했습니다.

### 검증

- Python agent/MCP 검사 **363건 통과**. 신규 회귀 검사 3건으로 원문 메타데이터, 플랫폼 분리, 고유 조항 식별, Figma/회수 검색, 원문 발췌·해시 검증, 생성물 재현성을 확인했습니다. 최종 정책 설명 정리 후 신규 3건도 다시 통과했습니다.
- Java main/test 오프라인 컴파일 통과. 기존 `Phase2FoundationIT`에 정책 SQL 2회 적용, 연결 버전 수, 기존 mock 가격·v1 권한 보존 검사를 보강했으나 실제 PostgreSQL 통합 실행은 환경 제한으로 미실행입니다.
- 생성 파일 검증과 `git diff --check` 통과. 적용 방법은 `data/phase2/policies/README.md`에 있습니다.

## 최종 시나리오 v4·첨부 이미지 대조 리뷰 — 2026-10-23

### 범위와 결론

- 수신 `UnlockOps-Phase-2-Test-Scenarios_근거반영_v4.md` 전체와 첨부 `image(8).png`의 9개 지적을 현재 작업 트리 기준으로 대조했습니다. 이번 작업은 리뷰이며 업무 코드·계약·DB·평가 기대값은 변경하지 않았습니다.
- 승인 2/3/4단계, 보류·재개, 기존 권한 안내, 부여 후 검증, 회수 후보/제외/유지/중복 알림 및 퇴사자 판정의 기본 흐름은 구현돼 있습니다. 다만 v4 전체와 일치하지 않으며, 기존 25건 평가가 통과하더라도 v4 충족을 의미하지 않습니다. 실제 DB·큐를 포함한 통합 시연은 이번 리뷰에서 실행하지 않았습니다.

### 우선 정합화할 차이

1. **회수 정보 부족과 실패 계약**: v4 X-08b는 신규 0건·추가 확인 1건 이상이면 `DONE / SCAN_COMPLETED`입니다. 현재 `agent/unlockops/reclaim/graph.py:finish`, `ReclaimResultService`는 `MANUAL_REVIEW / MISSING_SOURCE_EVIDENCE`로 처리합니다. `ReclaimRunView`, Java `Phase2Codec`, V6의 `reclaim_runs` CHECK도 `DONE`에 `needs_review_count=0`을 요구합니다. 서버만 고쳐서는 안 되며 새 migration·공통 계약·생성물·에이전트·화면·평가를 함께 갱신해야 합니다. 전체 정책/규칙 확보 실패도 현재 `MANUAL_REVIEW`이고, 담당자 미지정은 `MANUAL_REVIEW / APPROVER_UNAVAILABLE`입니다. 개별 사실 부족, 전체 점검 불가, 필수 알림 실패를 분리해야 합니다.
2. **v4 가격과 RAG 적용 데이터**: P-06은 Figma 월 16달러·예산 100→84인데 `data/phase2/catalog.json`과 기존 seed는 15달러·100→85입니다. 지난 RAG import의 revision 2도 기존 가격을 복사하므로 가격 차이는 남습니다. 기존 immutable revision을 UPDATE하지 않고 새 연결 revision으로 반영해야 합니다. RAG import SQL은 준비돼 있으나 실행 중 DB 적용은 확인되지 않았고, 평가 실행기는 여전히 revision 1 seed만 복제합니다.
3. **평가 입력과 근거 채점**: `scripts/phase2/fixtures.py`는 대부분 자연어 시나리오 대신 내부 권한 코드와 명시적 entitlement ID를 전달합니다. `run_suite.py`의 근거 검사는 존재 여부 중심이며 v4의 POL/공식 요약별 조항 적중을 채점하지 않습니다. 따라서 자연어 해석과 새 RAG 근거를 통과했다고 볼 수 없습니다. `편집 권한`은 현재 해석기에서 `Can edit`이 되지만 Figma `EDITOR_SEAT`·Databricks `NOTEBOOK_JOB_USER`와 일치하지 않아 명시 ID 없는 요청이 권한 선택에서 탈락하는 것을 재현했습니다. 검증된 플랫폼별 역할 매핑이 필요하며 다른 권한으로 무조건 대체해서는 안 됩니다.
4. **회수 LLM 호출 범위**: v4는 신규 후보만 설명하고 신규/추가 확인 모두 0건이면 LLM 호출을 생략합니다. 현재 `compose_reports`는 제외·기통지 여부와 관계없이 앞쪽 항목들에 `report`를 호출하고, 이 함수는 LLM 모드에서 모델을 사용합니다. 조회한 알림 이력도 이 호출 제외 조건에 사용하지 않습니다. R-02/R-03/R-04처럼 결과가 신규 0건이어도 호출할 수 있습니다.
5. **최소 권한 제안의 목적 검증**: B-02는 코드 열람 목적일 때만 Admin→Read를 제안합니다. 현재 `phase2_selection.py`는 Admin/Owner/Maintain/Full access를 목적 검사 없이 Read 후보로 좁힙니다. B-02 fixture도 열람 목적 없는 Admin 요청입니다. 요청 목적에 Read가 충분한지 확인하는 양성/음성 조건을 맞춰야 합니다.
6. **여러 플랫폼 요청(X-12)**: v4는 첫 플랫폼 GitHub만 처리하고 Jira 별도 접수를 안내합니다. 현재 `planner.py:interpret`의 LLM 지시는 여러 플랫폼 변경 요청을 out_of_scope=true로 분류하며, v2 그래프는 이를 수동 검토로 중단합니다. 첫 플랫폼 선택·나머지 플랫폼 별도 안내를 보장하는 계약/평가가 필요합니다.

### 첨부 이미지 9개 항목에 대한 확인

| 이미지 번호 | 확인 결과 |
|---|---|
| 1. v2는 DB 정책 revision 사용 | 맞습니다. 지난 작업에서 `data/phase2/policies/` 원문·회사별 묶음·새 revision 적용 SQL과 MCP 검색을 마련했습니다. v1 파일 교체만으로 반영되지 않습니다. 실제 DB 적용은 별도 확인이 필요합니다. |
| 2. 가격은 합성 계약, 새 revision 필요 | 맞습니다. Figma 16달러 미반영이며 정책 import는 가격 수치를 그대로 복사합니다. V6 immutable trigger 때문에 기존 revision 직접 수정은 불가합니다. |
| 3. 정보 부족은 현재 MANUAL_REVIEW | 맞습니다. v4와 명확한 충돌이며 DB/계약/평가까지 변경 대상입니다. X-UNKNOWN/X-COST 기대값도 이전 규격입니다. |
| 4. PARTIAL 및 내부 상태 매핑 | 현재 repo에는 QUEUED/RUNNING/REPORT_READY/PARTIAL 실행 상태가 없고 공통 상태를 직접 저장합니다. 페이지 누락·상한 초과는 그래프 오류로 실패 처리하며 부분 결과를 저장·반환하는 계약은 없습니다. 별도 회수 구현의 어댑터 요구인지 구분해야 합니다. 추가로 서버에 scan_complete=false 결과가 직접 오면 현재 MANUAL_REVIEW로 처리하므로 이 분기도 v4와 다릅니다. |
| 5. ALREADY_HAS_ACCESS와 result_type | 현재 `DONE / ALREADY_HAS_ACCESS`, `result_type=GUIDANCE`, `verification_ok=null`로 이미 처리됩니다. result_type은 추가 구분 필드라 v4와 충돌하지 않습니다. 회수는 별도 reclaim_runs 테이블이므로 이 이유만으로 problems의 result_type 제약을 제거할 필요는 없습니다. |
| 6. 추가 확인 응답 필드 | 실행 응답에는 최상위 needs_review_count, overview에는 summary.needs_review_count, 항목에는 review_required가 있습니다. v4의 needs_review[{employee_name, resource_name, missing[]}] 구조는 없습니다. 화면도 현재 ‘근거 확인 필요’입니다. 필드 중복 신설보다 기존 계약과 통합해 확정해야 합니다. |
| 7. PLAN_REVIEW_REQUIRED | 실제 서버가 계획/조건 변경 시 사용합니다. 현재 공통 최소 사유 목록에는 등록되지 않았습니다. ANALYSIS_CONFLICT도 서버 사용 코드이므로 함께 문서화해야 합니다. |
| 8. 추가 평가 ID | 맞습니다. 실행기는 X-10, X-UNKNOWN, X-4STEP, X-11, X-COST입니다. X-4STEP은 v4 X-03에 대응하고 X-UNKNOWN/X-COST는 X-08b 하위 사례로 정리할 수 있습니다. 다른 X 항목 일부는 기존 평가 내부 검사와 겹치므로 누락과 이름 차이를 구분해야 합니다. |
| 9. 자동 점검 기본 비활성 | 맞습니다. 실제 토글은 PHASE2_RECLAIM_SCHEDULE_ENABLED=false이며, seed의 reclaim_scopes.enabled도 false입니다. 두 조건을 켜야 09:00 Asia/Seoul 스케줄이 동작합니다. DEMO_ENABLED는 수동 실행 허용 설정입니다. 현재 시각은 @Scheduled에 고정돼 있어 v4의 시각 설정값 요구와도 차이가 있습니다. |

### 작은 재현 검사와 권장 순서

- 기존 scan_done_empty 예제를 `SCAN_COMPLETED`, `needs_review_count=1`로 바꾸어 Python 계약 검증: `Incomplete scan/review/notification cannot be DONE`으로 거절됨을 확인했습니다.
- 모델 대신 설명 함수 spy를 사용한 검사: 제외 항목만 1개인 경우와 기통지 항목만 1개인 경우 모두 설명 생성 함수가 1회 호출됐습니다. 외부 LLM은 호출하지 않았습니다.
- Figma·Databricks 편집 자연어 요청을 기존 catalog 권한 선택 함수에 전달: `Can edit`과 내부 권한 코드 불일치로 선택 실패를 확인했습니다. 새 테스트 파일은 추가하지 않았습니다.
- 권장 순서: (1) 회수 상태/정보 부족/실패 계약 확정·동시 반영 → (2) v4 RAG·가격·역할 매핑과 평가 데이터 정합화 → (3) 신규 후보만 LLM 호출, 목적 기반 최소 권한 제안 → (4) 시나리오 ID·근거 채점·스케줄 설정 정리 후 실제 스택 시연 검증.

## 시나리오 v4 정합화 구현 — 2026-10-23

위 대조 리뷰 이후 수행한 변경입니다. 이전 리뷰는 변경 전 상태의 기록이며, 이 절이 현재 구현 기준입니다.

### 변경 내용과 의도

| 영역 | 변경 내용 | 의도 |
|---|---|---|
| 회수 상태 | 정보 부족은 추가 확인 목록으로 분리하고 DONE/SCAN_COMPLETED. 신규·추가 확인 모두 0건만 NO_NEW_CANDIDATES | 정보 부족 한 건 때문에 전체 정상 점검을 수동 검토로 중단하지 않음 |
| 실패·부분 조회 | 전체 조회 실패·상한 초과·정책 확보 실패는 FAILED/SCAN_FAILED. 검증 가능한 부분 행은 scan_complete=false로 저장하고 알리지 않음 | 부분 결과를 전체 완료·0건으로 오인하지 않음 |
| 필수 알림 | 담당자 미지정은 FAILED/NOTIFICATION_FAILED. 성공 이력은 보존하며 미통지 기존 후보도 재점검에서 신규 알림 대상으로 계산 | 실패한 알림과 정보 부족을 구분하고 재점검으로 전달 복구 가능 |
| 공통 응답·화면 | summary 카운트와 needs_review 목록에 직원·자원·missing 코드 추가. ‘추가 확인’ 문구 사용 | 어느 정보를 보완해야 하는지 확인 가능. 기존 최상위 카운트는 호환 유지 |
| LLM 호출 | 신규·확정·미통지 후보만 설명 생성. 제외·유지·기통지·정보 부족은 검증된 템플릿 사용 | 후보 0건일 때 불필요한 호출 방지 |
| DB·정책·가격 | V8 migration과 opt-in revision 3 추가. Figma 16달러, 100→84 예산 반영. 원문·revision 1/2 보존 | 과거 승인 계획/스냅샷을 바꾸지 않고 v4 자료를 연결 |
| SaaS 사실 | Databricks Run as 주체/데이터 접근 사실, 플랜명, 모의 TF 자원 범위 명시. Tableau ANALYST 기준 | v4 전제조건을 실제 서버 검사와 모의 데이터에 반영 |
| 자연어 해석 | 플랫폼별 Can Edit/USAGE/Read Only 등의 별칭을 허용된 mock 권한 코드에 매핑 | 명시 entitlement ID 없이도 시나리오 문장 처리. Viewer를 Editor로 대체하는 기존 결함은 재발 방지 |
| 최소 권한 | GitHub 코드 열람 목적이 확인되고 변경 목적이 없을 때만 Admin→Read 제안 | 요청 목적을 해결하지 못하는 권한을 자동 제안하지 않음 |
| 여러 플랫폼 | 첫 명시 플랫폼만 서버 요청 범위로 저장하고, 에이전트에도 그 구간만 해석하도록 전달. 나머지는 별도 접수 안내 | X-12에서 두 플랫폼의 권한을 함께 변경하지 않음 |
| 개인정보 | 요청 저장·감사 payload·MCP 전달 전에 전화번호/이메일/명시 주소·도로명 주소 형식 마스킹 | X-07의 입력 개인정보가 보고서로 그대로 전달되지 않음. 자유형 개인정보 전체를 탐지하는 DLP는 아님 |
| 근거·평가 | 승인 근거를 검증된 개별 조항으로 보존하고 회수 근거도 조항으로 분리. v4 자연어·근거 조항·revision 3으로 평가 | 상태값만 맞고 입력 해석·근거는 검증하지 못하던 공백 보완 |
| 스케줄·사유 | PHASE2_RECLAIM_CRON 설정 추가(기본 09:00 KST), PLAN_REVIEW_REQUIRED/ANALYSIS_CONFLICT 등록 | 시나리오·문서·실제 서버 코드의 용어 통일 |

### 적용 파일과 실행 순서

- `V8__reclaim_v4_completion.sql`: 회수 CHECK 제약과 기존 MANUAL_REVIEW 실행 이력 변환, SaaS 추가 사실 필드. V1~V7 파일은 수정하지 않았습니다.
- `scripts/align_phase2_v4.py`: `data/phase2/policies/company-*-policy-v3.md`, `apply-v4.sql`, `data/phase2/scenarios-v4.json` 생성. 가격의 공식/가정 구분은 수신 문서 기준이며 공식 웹 원문을 재검증하지 않았습니다.
- 새 시연 DB: 백엔드 V8 적용 → `data/phase2/seed.sql` → `data/phase2/policies/apply.sql` → `data/phase2/policies/apply-v4.sql`. 이미 revision 2가 있으면 마지막 SQL만 적용합니다. revision 3 이후 이전 apply.sql을 다시 실행하지 않습니다. 자동/수동 구분과 확인 쿼리는 [정책 적용 안내](data/phase2/policies/README.md#시연-db-적용-절차와-확인)를 따릅니다.
- 서버·Worker/MCP·프론트 계약을 함께 배포해야 합니다. 새 요청/재분석/새 점검부터 새 revision을 사용합니다. 과거 계획은 최신 조건 검사에 따라 재검토가 필요할 수 있습니다.
- 자동 점검은 기본 비활성을 유지합니다. 시연은 DEMO_ENABLED 수동 실행이며, 정기 실행하려면 PHASE2_RECLAIM_SCHEDULE_ENABLED와 대상 reclaim_scopes.enabled를 모두 켭니다. 실제 회수와 외부 Slack/메일 발송은 수행하지 않습니다.
- 핵심 평가 20건은 `scenarios-v4.json`, 추가 검증 8건은 fixtures입니다. X-08b-USAGE/COST, X-03으로 ID를 맞추고 X-07/X-08/X-12를 추가했습니다. 기존 catalog/seed는 baseline-v1 비교용으로 보존합니다.

### 검증과 남은 실행 확인

- Python agent/MCP **368건 통과**, 평가 데이터 준비 **3건 통과**, 프론트 상태 표시 **3건 통과**. 기존 검사 보완과 자연어/LLM 생략 경계 검사 2개를 추가했습니다.
- Java main/test 오프라인 컴파일 및 핵심 워크플로 5건·공통 계약 2건 직접 실행 통과. 추가 확인이 있는 DONE과 회수 MANUAL_REVIEW 금지는 Python/Java 공통 벡터에 포함했습니다.
- `Phase2FoundationIT`에 revision 3 이중 적용·Figma 16달러·Run as 사실·v4 DB 상태 제약 검사를 보강했습니다. 실제 PostgreSQL/브로커를 사용하는 통합 실행 및 실행 중 DB 적용은 아직 수행하지 않았습니다.
- 수정한 ReclaimRun.vue는 캐시된 Vue 컴파일러로 script/template 구문 검사를 통과했습니다. `npm run build`는 로컬 vue-tsc 미설치로 실행하지 못했습니다. 지정 버전 의존성이 설치된 환경의 프론트 전체 빌드·브라우저 시연과 smoke/full 통합 평가가 남습니다.
- 현재 권한 실행은 mock입니다. 플랫폼별 공식 역할의 실제 SaaS API 적용, 임의 형식 개인정보의 완전 탐지, 외부 알림 전달은 이번 변경으로 구현됐다고 간주하지 않습니다.

## 다음 작업

1. Docker 및 패키지 다운로드가 가능한 환경에서 smoke → full을 실행하고 FAIL/BLOCKED를 해결합니다. 수동 GitHub workflow로도 실행할 수 있습니다.
2. 위 브라우저 시연 항목과 기존 데이터 복제본의 V5→V8 업그레이드를 확인합니다.
3. 수신 RAG와 v4 가격 revision 3을 적용하고, 동일 입력·기대값의 기준선과 비교해 변화와 에이전트 품질을 확인합니다.

## 작업 이력

| 날짜 | 작업 | 의도·결과 |
|---|---|---|
| 2026-10-22 | 베이스라인 1단계 | 기존 v1 실행 보존, v2 계약·DB·mock 기반 마련. DB 통합 검증은 환경 제약으로 남음 |
| 2026-10-22 | 베이스라인 2단계 | 서버 승인·보류·재개·모의 부여·회수/알림 API, v2 큐/결과 경계 구현. 핵심 테스트 4건 추가·통과. Worker/MCP 연결과 실제 DB 통합 실행은 남음 |
| 2026-10-22 | 베이스라인 3단계 | 승인 분석/실행·회수 그래프, v2 MCP·정책 revision RAG·Worker 연결. 핵심 테스트 5건 추가, 전체 Python 355건 통과. 실제 DB·브로커 통합은 남음 |
| 2026-10-22 | 베이스라인 4단계 | v2 승인·회수 화면, 계정별 진입·조회 projection·접수 재시도 연결. 핵심 테스트 3건 추가, 실행 가능한 프론트 19건 통과. 지정 버전 빌드·브라우저·전체 스택 검증은 환경 제약으로 남음 |
| 2026-10-22 | 베이스라인 5단계 | 25건 격리 평가 실행기·전용 Compose·수동 CI·시연 기준 연결. 신규 오프라인 3건 및 기존 Phase 2 34건 통과. 실제 전체 실행은 Docker 미기동으로 BLOCKED |
| 2026-10-22 | 1~5단계 전체 코드 리뷰 | 미해결 결함 5건(CR-01~05) 기록. 업무 코드 수정 없음. Python 355건·프론트 3건·평가 준비 3건 및 Java 컴파일 확인. 경계 오류 별도 재현 |
| 2026-10-22 | CR-01·CR-02 개선 | 역할 불일치 시 수동 검토, 결정 API에 계획 버전 검증 추가. 계약·프론트·평가 호출자 동시 갱신. Python 39건·Java 7건·프론트 3건·평가 준비 3건 통과 |
| 2026-10-23 | DB 구조 시각화 | V1~V7 DDL을 기준으로 `docs/images/phase2/database-overview.png` 작성, `docs/schema.md`에 연결. 권한 목록과 직원 할당, 가격과 예산, 승인 회차와 회수 스냅샷을 구분해 설명. 업무 코드·DB 변경 없음 |
| 2026-10-23 | 수신 RAG 문서 연결 | 28개 문서·107개 청크 파싱, 회사별 정책 revision 2와 연결 버전 적용 SQL 생성, 플랫폼별 검색 및 인용 개선. Python 363건·Java 컴파일 통과. 실제 DB 적용은 환경 권한 제한으로 미실행 |

| 2026-10-23 | 시나리오 v4 정합화 | 회수 완료/추가 확인/실패 계약, V8 migration, 정책·가격 revision 3, 자연어 권한 매핑·최소 권한 목적 검사·첫 플랫폼 처리·마스킹·평가셋 정합화. Python 368건, 평가 준비 3건, Java 핵심 7건, 프론트 3건 통과. DB 적용·전체 프론트 빌드·통합 시연 미실행 |


## 2026-10-23 회수 AI 역할 분리 및 보고서 보완

사용자 요청에 따라 AI 코드만 수정했습니다. 프론트·Spring·공통 계약 생성물은 변경하지 않았습니다.

- `agent/unlockops/reclaim/`를 `graph.py`(연결·이벤트), `state.py`(상태), `context.py`(점검 준비), `policy.py`(RAG), `scan.py`(대상·알림 이력), `reporting.py`(설명·검증·보고서)로 나눴습니다. 파일명에 `phase2_`는 붙이지 않습니다.
- 그래프는 `context → policy_review → candidate_review → report_writer → finish`이며, 기존 Worker 진입점·노드 이름·체크포인트 키를 유지합니다. POL-06 제5조를 필수 조회하고 원문·조항·revision·해시가 일치하는지 검증합니다.
- 별도 AI 보고서에 `candidates`, `summary.needs_review_count`, `needs_review[{user_name, platform, missing}]`를 구성합니다. 현재 서버 큐의 엄격한 `result/targets` 계약은 유지하며, 공개 S-04 응답 연결은 백엔드 담당자의 후속 작업입니다.
- 부분 실패는 `FAILED / SCAN_FAILED`와 검증된 부분 결과를 보존합니다. 모델은 설명만 보완하며, 실패하면 정형 문구를 유지합니다. 판정·금액·근거·대상 식별자가 바뀌면 차단합니다. Agent는 DONE이나 실제 회수를 확정하지 않습니다.
- 현재 MCP에 없는 이름·마지막 사용일·상세 누락 항목은 추측하지 않습니다. 신뢰할 수 있는 별도 사실 메타데이터가 제공될 때 보고서에 보완할 수 있습니다.
- 검증: 전체 Python 테스트 **392건 통과·1건 건너뜀**, 공통 계약 생성물 일치 확인 통과. 실제 DB·브로커·LLM·프론트 통합 실행은 수행하지 않았습니다.

## 승인 RAG 문서 점검과 보고서 근거 보강 — 2026-10-23

- 수신 POL 14개·공식 요약 14개, 회사별 정책 묶음 revision 3, 검색·승인 보고서 연결을 대조하고 `docs/rag-approval-review.md`에 역할·지원 차이를 정리했다. 정책·가격·승인 경로의 immutable revision은 보존했다.
- `approval-review-guide.md`를 추가해 생성·내용 검토 양쪽에 연결했다. 규정·공식 제품 참고·회사 승인 경로·시연 가정의 역할, 승인자별 검토 항목, 정보 부족·최소 권한·비용 표현과 지원 한계를 명시했다. 지침은 회사 규정 검색 원문에 섞지 않고 Python 패키지에 포함한다.
- 승인 근거에서 회수 조항을 제외하고 GitHub 좌석/저장소 및 TF 적용 범위를 구분한다. article 제목과 실제 원문, 플랫폼, 회사 묶음 해시·버전, 승인 계획의 정책 ID·revision을 대조한다.
- 내부 assessment 응답에 선택적 `review_facts`를 추가했다. 정상 계획과 예산 부족 시 자원·권한·TF 확인·금액·통화·잔여 예산·단가 출처·조회 시각을 전달한다. 공개 workflow 계약·계획 해시·승인 순서·실행 권한은 바꾸지 않는다. 새 응답 필드를 이해하도록 Backend·Business MCP·Agent를 함께 갱신한다.
- 보고서는 서버 사실로 예산 영향을 계산하며 누락된 값을 문서 예시로 채우지 않는다. 직원 ID·이름·로그인·이메일·요청 원문·제공자 내부 참조는 모델 facts에서 제외한다. 모델·인용·검토 실패 시 같은 사실로 만든 템플릿을 사용한다.
- 검증: 전체 Python **378 passed, 1 skipped**. 이후 예산·TF 모순 응답 음성 검사 3건을 추가해 승인 관련 **25건 통과**. 원문 import/v4 생성 결과 검사와 `git diff --check` 통과. Java main/test 컴파일 및 신규 planning 1건·기존 workflow 5건·공통 계약 2건을 로컬 직접 실행기로 실행해 **8건 통과**했다. 기본 Maven test는 캐시의 Surefire 3.5.4 의존성 부족으로 실행되지 않았다. 깨끗한 임시 소스에서 wheel을 빌드하고 지침·검색 모듈 포함을 확인했다.
- 실제 모델·SaaS·DB·브로커 통합 실행과 서비스 재배포는 하지 않았다. 단계별 최신 보고서 재생성, 문서의 세부 자격 조건과 서버 검사 전체 정합화, 공식 제품 문서·가격의 최신성 재검증은 점검 문서에 남은 범위로 구분했다.

## 승인·회수 실행 구조 통합 — 2026-10-23

### 범위와 결과

사용자 요청에 따라 프론트 소스·공개 API/응답 계약은 유지하고 서버·에이전트·Worker·MCP를 현재 업무 흐름으로 통합했다.
기존 단일 승인 실행기와 Phase 2 실행기를 함께 유지하던 구조를 제거했다. 승인 분석·승인 후 실행·회수의 업무 구분은 유지한다.
진행 중이던 승인 RAG 보고서 보강(review_facts, 검토 지침, 근거 선택·인용 검증)도 보존했다.

| 이전 위치·구현 | 현재 위치·처리 |
|---|---|
| 구 access/graph.py와 phase2_graph.py 병존 | access/graph.py 하나로 분석·문서 안내 통합 |
| phase2_execution.py | access/execution.py |
| phase2_intent/selection/review.py | access/intent.py, selection.py, review.py |
| common/phase2.py와 구 Job/Plan/Result | common/workflow_contracts.py. Intent·ToolFailure는 공통 models 유지 |
| phase2_tools/runtime/reporting.py | common/tool_contracts.py, runtime.py, reporting.py |
| planner의 모델 설정 | common/llm.py를 해석·선택·안내·보고서에서 공유 |
| backend phase2/access·reclaim | backend access·reclaim 업무 패키지 |
| Phase2Store/AccessControl/Jobs/Results | common/workflow와 messaging/workflow의 Workflow* |
| Phase2Types/Codec | contracts/v2의 WorkflowTypes/WorkflowCodec |
| worker의 v1 interrupt/resume와 phase2.py | runtime.py와 단일 소비·발행 경로 |
| 구/신 MCP 도구·어댑터 병존 | 현재 business_tools/policy_tools와 WorkflowBackend, 공유 BackendClient |

### 유지한 기능과 제거한 실행 경로

- 규정·공식 제품 요약·진단 힌트로 권한/접근 문의를 안내하는 기능을 현재 분석 그래프에 연결했다. 기존 answering의 인용·원문·내용 검토를 재사용하고 response_context를 현 서버 사실·회사별 정책에 맞췄다. 문서에 없는 SSH/remote·제품 테마 절차는 안내하지 않는다.
- GUIDE는 승인·권한 변경 없이 DONE/GUIDANCE로 완료한다. 필요한 권한을 이미 가진 TROUBLESHOOT도 안내로 연결한다. 직접 권한 신청의 기존 권한 보유 응답은 간단한 안내를 유지한다. 안내 근거 부족·모델 장애는 수동 검토다.
- 구 그래프·역할 규칙·권한 제안 구현, 구 서버 접수/단일 승인/부여/내부 API와 관련 DTO·repository, 구 MCP 도구·도구 계약을 제거했다.
- 공통 MCP 연결·HTTP 인증/오류 처리·검색 유틸·입출력 검증·작업 범위/실행 허가·호출 한도·재시도·checkpoint 결과 재사용·outbox/inbox를 유지했다.
- Worker는 기존 이름의 v2.analysis/v2.execution만 소비한다. 서버 outbox도 현재 경로만 발행한다. 구 메시지·체크포인트·DB 이력을 삭제하거나 새 계획으로 재해석하지 않는다.
- 모든 로그인 프로필은 workflow_version=2로 현재 화면을 선택한다. 시연 A/B사 계정과 ID를 유지한다. 구 회사의 권한 데이터를 새 할당 모델로 자동 복사하지 않으며 과거 대기 업무는 최신 조건으로 재접수한다.
- 공개 /api/v2/problems·/api/reclaim, schema_version=2, frontend/src/contracts/phase2.ts, 계획 hash·승인 버전·정책 revision은 보존했다. 기존 생성기·계약/데이터 fixture 경로도 호환을 위해 유지한다.
- Compose 시연 데이터 준비를 baseline → 누락된 정책 revision 2 → revision 3으로 통일했다. Spring 트랜잭션 내에서 PostgreSQL에 전체 SQL을 전달해 dollar-quoted DO 블록을 보존한다. 이미 설치된 revision은 덮어쓰지 않는다. 시연 밖에서는 준비하지 않는다.
- 적용된 Flyway V1~V8·원문·생성 정책 SQL·과거 승인/회수 이력은 수정하지 않았다. 실제 실행 DB·큐·서비스 재배포도 수행하지 않았다.

### 검증과 남은 확인

- Python Agent/MCP/live 선택 검사/평가 준비 **194 passed, 1 skipped**. 안내 생성·지원 범위·인용/내용 검토·모델 실패·도구 범위/한도·실행 식별자·재전달·실제 MCP HTTP 경계를 현재 흐름으로 검사했다.
- 업무/HTTP 계약·정책 import·v4 생성물 일치 검사 통과. 프론트·migration 파일 변경 없음.
- Java main 49개/test 10개 소스 독립 컴파일과 JUnit **28건 통과**. 계약·승인/회수·보고서·시연 인증·SQL 블록 보존/재시작·메시지 경계·HTTP 보안 포함. IDE 출력 폴더와 분리한 javac/JUnit 실행으로 확인했다.
- 기본 Maven test와 캐시된 Surefire 3.5.6 실행은 필요한 플러그인/provider 캐시 부족으로 실행 불가했다. JUnit 직접 실행을 표준 Maven 실행 성공으로 기록하지 않는다.
- 기존 프론트 npm test는 19건 통과했고 requesterHome 검사는 @vue/compiler-sfc 미설치로 시작 실패했다. 프론트 소스·의존성 파일은 변경하지 않았다.
- Docker 소켓 접근 거부로 실제 PostgreSQL·RabbitMQ 스택·smoke/full·브라우저 시연은 미실행이다. 실제 SaaS·유료 모델 호출도 하지 않았다.
- 기존 CR-03/04/05와 세부 정책 정합화는 별도 결함/업무로 유지한다. 구조 이동으로 해결됐다고 간주하지 않는다.

현재 구조는 docs/architecture.md, API는 docs/api-spec.md·contracts/phase2/http.json, 실행 검증은 docs/verification.md를 따른다.

## 기존 계정·과거 요청 연결 — 2026-10-23

통합 리뷰의 첫 번째 결함을 수정했다. 화면만 현재 흐름으로 바뀌고 기존 조직의 정책·권한·보유 내역이 비어 있던 문제와 과거 요청 조회 누락이 대상이다.

- Flyway V9를 추가했다. 기존 LEGACY mock 조직의 원래 네 플랫폼(GitHub/Jira/Slack/Notion)에 정책 원문·권한/가격 revision·현재 순차 승인 경로·담당자 매핑·계정 사실을 준비한다. A/B사 데이터·적용된 V1~V8은 수정하지 않는다.
- 계정·자원 ID, 비밀번호, 잔여 예산, 원래 permissions·팀 멤버십·과거 요청/영수증을 보존한다. 현재 보유 권한은 access_assignments와 현재 mock 제공자 상태로 이관한다. 이관 시 예산을 재차 차감하지 않으며 사용량은 UNKNOWN이다. GitHub 팀 연결과 Jira Browse 조건을 원래 조회 기준대로 확인한다.
- 기존 직무·직급 상한은 immutable mapping의 allowed_job_families/allowed_job_grades/grantable로 유지한다. NON_DEV를 OPS 등으로 임의 변환하지 않고, 이관 매핑이 명시한 네 플랫폼에서 기존 job_family로 판정한다. 다른 회사의 UNKNOWN 처리 기준은 유지한다.
- 부서장과 문서에 명시된 기존 SaaS 담당자(song_ops)를 연결한다. 본인 승인·중복 승인자·담당자 미지정은 수동 검토한다. 기존 좌석 단가·통화가 부서별로 상충하면 단가를 추측하지 않고 가격 확인이 필요하다.
- 현재 목록·상세 API에서 허용된 과거 요청을 읽는다. 과거 지정 승인자/기록된 결정자도 같은 회사의 해당 기록만 읽는다. 과거 plan과 evidence는 historical_record와 감사 이력으로 보존하며 현재 실행 계약으로 해석하지 않는다.
- 과거 대기 건은 재분석 필요로 표시한다. 재개 시 같은 ID의 원본을 감사 이력에 저장하고, 이전 승인·해시·실행 키를 제거한 뒤 contract_version=2의 새 ANALYZE를 발행한다. 완료·반려·실패 기록은 재실행하지 않는다. Worker와 내부 실행 API는 계속 현재 계약만 처리한다.
- 프론트 소스·생성 계약·기존 migration은 변경하지 않았다. 기존 Notion 보기 요청은 이관된 VIEWER 코드로 해석하도록 alias를 연결했다. 리뷰의 안내 생성·스케줄 설정 문제는 이번 수정 범위에 포함하지 않는다.

검증: Python **199 passed, 1 skipped**, Java 소스 독립 컴파일 및 JUnit **36 passed**, 계약/정책/v4 생성물 검사와 diff 공백 검사 통과. Flyway PostgreSQL 파서가 V9 전체를 13개 문장으로 정상 분리했다. 이는 PostgreSQL 실행 검증을 뜻하지 않는다.

실제 DB 업그레이드·이력·신규 순차 승인·중복 좌석·동일 실행 재전달 시 예산 1회 차감을 검사하는 ExistingAccountsMigrationIT를 추가했다. Docker 소켓 접근 거부와 로컬 PostgreSQL shared memory 생성 권한 제한으로 실제 DB 통합 실행은 미검증이다. 배포 DB에는 적용하지 않았다. 실행 가능 환경에서는 `cd backend && mvn verify -Pregression -Dit.test=ExistingAccountsMigrationIT`로 확인한다.

## 회수 Agent 변경과 실행 구조 통합 병합 — 2026-10-23

- main의 `workflow_contracts`, `tool_contracts`, `runtime`, `reporting`, `WorkflowTools`와 `max_reclaim_candidates`/`max_result_bytes` 이름으로 회수 모듈·Worker·테스트를 연결했다. 삭제된 phase2 실행기를 복원하지 않았다.
- 회수의 `context → policy_review → candidate_review → report_writer → finish` 역할 구조, POL-06 제5조 필수 조회·원문 검증, `candidates`/`needs_review` 별도 보고서, 부분 실패 시 검증된 결과 보존을 유지했다. 서버 큐의 `result/targets`와 최종 DONE·알림 결정 경계도 그대로다.
- Worker를 `unlockops_worker/runtime.py`로 통합하면서 MCP cancel scope를 부모 Worker 작업에서 열고 닫는 수정과, 완료 체크포인트 재전달 시 MCP를 다시 열지 않는 동작을 보존했다. 문서는 main의 최신 설명에 회수 역할·응답 계약을 합쳤고 양쪽 구현 이력을 유지했다.
- 병합 후 검증: 회수·공통 워크플로 **37 passed**, 전체 Python 및 평가 준비 **224 passed, 1 skipped**. main에서 이전 실행기·테스트가 제거돼 병합 전 393건과 전체 검사 수가 다르며, 회수 설계 테스트는 모두 유지했다. 공통 계약·HTTP 계약·정책 import·v4 생성물 검사와 diff 공백 검사 통과.
- 이번 병합에서 Docker 서비스를 다시 빌드하거나 실제 LLM을 호출하지 않았다. 현재 실행 중인 컨테이너는 병합 전 빌드이므로 병합 후 실행 검증 결과로 간주하지 않는다. 병합 커밋·원격 푸시는 수행하지 않았다.
## R-04 초기 알림 보고서 조회 수정 — 2026-10-23 · #43

R-04의 '이미 전달한 알림' 시드는 후보와 알림만 준비하고 당시 보고서를 생략했다. 새 점검 전에는 후보 상세가 404를 반환하고 overview 목록에서도 빠졌다. 기존 평가는 점검 후에만 상세를 조회해 이 조건을 놓쳤다.

- `scripts/generate_phase2_seed.py`와 생성된 `data/phase2/seed.sql`에 명시적인 합성 과거 실행·스냅샷·보고서를 추가했다. 2026-10-21의 고정 사실, 정책 revision 1, 월 19 USD를 사용한다. 기존 target/episode/notification ID와 전달 시각은 유지한다.
- seed 재적용은 누락 이력만 INSERT하고 이미 저장된 보고서·스냅샷·알림/읽음·예산·권한을 덮어쓰지 않는다. 실제 권한 회수나 새 알림/Agent 작업을 만들지 않는다. API와 적용된 Flyway migration은 변경하지 않았다.
- `ReclaimSeedReportIT`가 실제 Spring HTTP와 일회용 PostgreSQL에서 점검 전 알림→보고서→목록, 다른 회사 403, 재적용/읽음/권한/예산 보존을 검사한다. 원본에서 상세 404와 report 부재로 실패한 뒤 수정본에서 통과했다.
- R-04 전체 스택 평가도 점검 전에 알림 상세와 overview를 검사한다. 평가 fixture 복제 시 새로 추가된 스냅샷·보고서 JSON 내부 날짜도 실행일에 맞춰 함께 이동하며, 정책 원문과 해시는 유지한다.
- 기존 `WorkflowFoundationIT`의 run 변경 검사는 생성한 테스트 run ID에 한정했다. 추가된 과거 이력 때문에 다른 행의 제약 위반으로 검사가 잘못 통과하거나 역사적 스냅샷을 변경하지 않도록 했다.

실제 검증 결과:

- 수정 전 기본 단위 43개·기존 DB 회귀 3개 통과. 새 HTTP 회귀는 기대한 200 대신 404로 실패했고 연결 report가 없음을 확인했다.
- 수정 후 단위 43개 및 `ReclaimSeedReportIT,WorkflowFoundationIT,CompletionMigrationIT,ExistingAccountsMigrationIT` DB 회귀 5개 통과. 명령은 `mvn verify -Pregression -Dit.test=ReclaimSeedReportIT,WorkflowFoundationIT,CompletionMigrationIT,ExistingAccountsMigrationIT`에 로컬 Docker API 1.44/Mockito javaagent 옵션을 사용했다.
- 평가 fixture 검사 3개, 생성기 재실행 일치·diff 공백 검사 통과.
- `BUILDKIT_PROGRESS=quiet python3 scripts/evaluate_phase2.py --run --suite smoke --keep`: 실제 프론트 nginx→Spring→RabbitMQ→Worker→Business/Policy MCP→DB의 8개 사례 PASS. R-04 초기 보고서 조회·읽음 멱등성·재점검 알림/episode 보존과 DB 부수효과를 확인했다. LEGACY 데이터 불변 검사와 프론트 테스트/빌드도 통과했다. quiet는 Docker 빌드 진행 로그가 평가 JSON stdout에 섞이지 않게 하는 실행 옵션이다.
- 별도 격리 DB에 수정 전 seed와 정책 revision 3을 설치한 뒤, 수정 seed만 두 번 재적용했다. 원본 R-04 ID의 상세 404→200/목록 표시를 확인했고 후보·episode·알림·전달/읽음 시각·할당·예산·revision 3이 유지됐다. 새 큐 작업은 0건이다.
- 로컬 결과: `test-results/phase2/213c94e9-07b9-43cf-adc7-7d330e192638/report.json`, `existing-seed-repair.json`. 검증은 별도 UUID 스택에서 실행했으며 사용자 실행 중 DB에는 적용하지 않았다. 실제 SaaS·실제 모델 호출·브라우저 클릭은 미검증이다.

기존 시연 DB 적용은 수정 seed 재적용 또는 `DEMO_SEED_PATH`를 사용하는 백엔드 재시작으로 수행한다. 정책 revision 3을 이전 revision으로 되돌릴 필요가 없다. 절차는 `data/phase2/README.md`에 기록했다. 전체 회수 조회 구조 개선과 기존 미해결 CR-03 등은 별도 작업으로 유지한다.

## 환경변수 예제 전수 조사·동기화 — 2026-10-23 · #53

현재 단계: 예제·문서 수정과 정적/Compose 설정 검증 완료. 이슈 #53에서 공유하고 main 대상 PR로 검토한다.

- Python 환경 접근(AST, `project_path` 포함), Spring YAML/Java 주입, Compose/Dockerfile, Vite, VS Code·CI·평가·선택 테스트와 README를 대조했다. 직접 참조 45개 중 자동화/내장 4개를 제외한 41개가 예제에 모두 안내되도록 했다. 설정의 기본값·우선순위·로컬/Compose 적용 범위와 제외 이유는 `docs/environment.md`에 정리했다.
- 할당 예시 누락 16개를 보완했다. `RECLAIM_SCHEDULE_ENABLED`, `RECLAIM_CRON`, `DEMO_SEED_PATH`, DB·RabbitMQ 연결 변수, `RABBITMQ_URL`, MCP 프로세스 host/port, Vite 모의 모드, 선택 live 검사 설정이 대상이다. 기존 예제에 MCP host/port는 이름 설명만 있었다.
- 예제의 정식 `RECLAIM_*` 설정을 활성 항목으로 두고 스케줄 기본값 `false`를 유지했다. 이전 `PHASE2_*`와 `DEMO_PHASE2_SEED_PATH`는 주석 별칭으로 보존했다. Compose는 구 스케줄 별칭을 전달하지 않으므로 기존 `.env`의 이름을 옮겨야 한다. Spring도 두 이름이 함께 설정되면 정식 이름이 우선한다.
- 소비 코드가 없는 `ACCESS_MATRIX_PATH`·`LOG_LEVEL`과 Compose에 전달되지 않는 루트 `TZ`를 예제에서 제거했다. 스케줄 시간대는 코드에서 Asia/Seoul 고정이다. `DATA_DIR`의 현재 미사용 필드와 `EMBEDDING_*`의 유틸 전용 범위, LangSmith의 로컬 라이브러리 설정 범위를 명시했다.
- 루트·Backend·Worker·MCP·Frontend·RAG·테스트 README와 문서 색인을 갱신했다. 프론트 설정은 `frontend/.env.local`에 두며, 공통 MCP 포트 지정은 두 로컬 프로세스 간 충돌을 일으킬 수 있음을 안내한다. 제품 로직·Compose 전달 정책·DB·외부 계약은 변경하지 않았다.

실제 검증 결과:

- 동일한 일회성 Python AST/placeholder 대조: 변경 전 할당 예시 누락 **16개 → 변경 후 0개**. 예제 활성/주석 할당 **52개**의 중복·공백/cron 인용 검사 통과.
- `docker compose --env-file .env.example config --format json`: 기본 스케줄 비활성·cron·시연 seed/DB 경로·내부 토큰 일치·Worker MCP URL/체크포인트 경로 확인.
- 프로세스 환경으로 `RECLAIM_SCHEDULE_ENABLED=true`, `RECLAIM_CRON='0 30 10 * * MON-FRI'`를 전달한 config에서 두 값이 backend에 보간됨을 확인. 구 `PHASE2_*`만 덮어쓰면 정식 예제 기본값이 유지되는 Compose 경계도 확인했다. 최소 프로세스 환경과 예제 파일만 사용해 사용자 `.env`와 분리했다.
- `docker compose --env-file .env.example -f compose.yaml -f infra/compose.debug.yaml config --format json`: backend 설정 일치와 localhost 공개 포트 확인. 새 문서의 로컬 링크와 추가한 환경변수 안내 링크, `git diff --check` 통과.
- 문서·예제만 수정하여 Maven/Python/frontend 실행 테스트와 DB·브로커·전체 스택·실제 모델 호출은 수행하지 않았다. Compose 파싱 검증으로 실제 스케줄 실행 성공을 주장하지 않는다. 사용자 `.env`·실행 서비스·DB는 변경하지 않았다.

다음 작업: PR 리뷰 후 병합. 기존 로컬 환경 사용자는 필요한 새 이름을 `.env`에 반영하고 서비스를 재생성한다. 이후 환경변수 변경 시 CONTRIBUTING의 예제·서비스 README 동시 갱신 규칙을 따른다.

## 담당자 확정 모의 권한 회수 백엔드 — 2026-10-23 · #56

현재 단계: 백엔드 및 API 전달 계약 구현 완료, main 대상 PR 준비. 사용자 지시에 따라 프론트 연동/버튼 구현은 제외하고 추가 테스트를 중단했다.

- ReclaimExecutionController → Service → Repository를 추가했다. 실행 가능 여부 조회, 담당자 확정 회수, 담당 범위 완료 영수증 목록을 공개 세션 API로 제공한다.
- 실행은 demo/mock 회사의 확정된 ACTIVE SEAT로 제한한다. 기존 조회 권한과 같은 회사·부서·플랫폼의 SAAS_OPERATOR 또는 IT_HEAD를 확인하며, 최신 점검과 현재 정책·사용·TF·유지 승인 사실을 재검사한다.
- Flyway V11은 후보 RECLAIMED/reclaimed_at, 후속 action_taken=REVOKED와 불변 reclaim_execution_receipts를 추가한다. 제공자 멤버십 삭제·할당 종료·열린 후보 종결·저장 상태 SELECT 검증·영수증 저장이 하나의 트랜잭션이다. 예산은 자동 환입하지 않는다.
- 회사 단위 기존 부여/점검 mutex와 행 잠금, 요청 키/입력 해시와 assignment당 UNIQUE로 중복 실행을 막는다. 회수 전 스냅샷의 지연 결과는 원본 보고서를 보존하되 후보·알림을 다시 만들지 않고 영수증 참조를 기록한다.
- 기존 보고서의 CandidateStatus/action_taken=NONE, 알림 읽음, 부여 영수증은 보존한다. 최신 보고서 탐색은 assignment_id를 기준으로 하여 뒤의 미확인 행으로 바뀐 후보를 과거 근거로 회수하지 못하게 한다. overview는 원본 보고서를 현재 ReclaimTargetView로 투영하여 회수 완료 상태를 표시한다.
- 신규 HTTP 모델·409 오류를 공통 계약 원본과 Java/TS 생성물·OpenAPI에 추가했다. 생성기의 boolean const는 AssertTrue/AssertFalse로 검증하도록 보완했다. frontend에는 생성 타입만 포함하고 연동/화면 코드는 포함하지 않았다.
- 프론트 담당자 전달 내용은 docs/reclaim-execution-api.md에 단일 문서로 정리했다. API·입출력·권한·nullable/enum·중복/응답 유실·409·DB 의미·현재 미검증 범위를 포함한다.

실제 검증 결과(추가 테스트 중단 요청 전):

- 변경 전 Java 단위 43개, 기존 DB 회귀 5개 통과. 기존 스냅샷 판정을 고정한 DB 테스트 1개를 제품 변경 전 통과시키고 테스트 기준 커밋으로 남겼다. 신규 API는 원본에서 404 실패를 확인했다.
- 구현 후 `mvn clean verify -Pregression -DargLine=-Dapi.version=1.44`: 단위 43개/DB·브로커 통합 18개 통과. 18개 중 회수 실행 테스트는 13개다. Docker 29의 최소 API 버전 옵션을 사용했다.
- Python Agent/MCP/계약/평가 준비 247개 통과. 공통 계약/HTTP 생성 검사 통과.
- 정상 제공자 삭제·제공자 없는 시드·권한/CSRF·입력/최신성·유지 승인·영수증 실패 롤백·동일/서로 다른 키 경합·이력 불변·시드 재적용·지연 inbox 결과·회수 후 재점검·새 할당 재부여를 검증했다.
- 전체 스택 full 평가는 Maven parent 다운로드 실패로 중단됐다. 검증된 로컬 JAR를 임시 런타임 이미지로 사용한 재시도도 evaluator JSON 보고서 생성 실패로 완료하지 못했다. 격리 스택/볼륨은 모두 정리됐고 사용자 서비스·DB는 변경하지 않았다. 보고서는 test-results/phase2/26e021c1-3e78-496a-ba14-ddf161cb07d2 및 b4d30b7c-50d3-40df-bf11-660c86ca8d18 아래 로컬 파일이다.
- 위 통과 후 409 오류를 명시적인 공통 생성 DTO로 정리했다. 이후 사용자의 테스트 중단 요청으로 최종 DTO 변경은 재실행하지 않았다. 실제 SaaS·실제 LLM·브라우저 클릭·최종 전체 스택 성공은 미검증이다.

다음 작업: PR 검토와 백엔드 배포 후 프론트 담당자가 전달 계약에 맞춰 /revocations의 버튼·완료 이력을 연결한다.

### 프론트 전달 계약 반영 — #56

- 사용자 제공 최종 계약을 반영했다. POST revoke는 Idempotency-Key와 빈 객체 {}만 받으며, 최신 대상/점검은 서버가 확인한다. 이미 처리된 후보는 같은 키 재전송도 409다.
- overview targets에 can_revoke, reclaimed_at을 추가하고 회수 완료 행을 RECLAIMED/action_taken=REVOKED로 유지한다. 현재 검토 건수/절감 예상 합계에서는 완료 행을 제외한다.
- V11의 대상/점검 행 candidate_status CHECK와 action_taken CHECK를 확장했다. 적용된 V1~V9와 원본 보고서 JSON/스냅샷은 변경하지 않았다. 후속 실행 메타데이터와 불변 영수증을 저장한다.
- 기존 보유 판정이 ACTIVE 할당만 조회하므로 회수 후 재신청은 새 승인 흐름을 사용한다. 서버 후보 설명과 Agent 작성 지침도 담당자 확인 후 회수할 수 있다는 문구로 맞췄다.
- 최종 계약에 맞춰 테스트/벡터를 갱신하고 계약 생성물을 재생성했으나, 사용자 요청에 따라 테스트는 실행하지 않았다. 앞선 43/18/247 통과 결과와 최종 변경의 미검증 범위를 구분한다.

## 권한 추가와 라이선스 비용 분리 — 2026-10-23

앞선 E-02 조건 보강은 기존 잘못된 비용 가정을 보존한 평가 개선이었다. 이번 변경은 실제 서버의 비용 판단과 실행 예산 반영을 수정한다.

- `AccessCosting`을 추가했다. 가격표의 참고 단가와 이번 요청의 예산 반영액을 분리하고 PERMISSION_ONLY / PURCHASE_SEAT / USAGE_ALLOCATION으로 판단한다. 기존 라이선스가 확인된 Notion・Tableau 권한 추가는 단가 20/70이어도 0원을 계획한다. 모호한 ROLE+SEAT_MONTHLY를 좌석 구매로 해석하지 않는다.
- V10은 immutable 정책・권한에 연결된 `access_cost_rules`, 회사・사용자・플랫폼・조직 범위・라이선스 코드별 `saas_license_facts`를 추가한다. 관측 누락・UNKNOWN・만료・미래 시각은 수동 검토다. 권한만 요청했는데 라이선스가 없으면 자동 구매하지 않는다. 좌석 미보유와 신규 구매 필요까지 확인돼야 단가를 적용한다. 미배정 좌석・업그레이드・일할 청구 자동 계산은 지원하지 않는다.
- 승인 단계와 최종 실행은 계산된 예산 반영액을 사용한다. 실행은 예산・라이선스 사실을 잠그고 최신 계획을 비교한다. 모의 좌석 확보 시 라이선스 관측도 같은 트랜잭션에서 COVERED로 갱신하며 멱등 영수증을 유지한다. 실제 SaaS 결제를 호출하지 않는다.
- `review_facts.cost_assessment`와 Python 도구 계약・보고서 지침을 보강했다. 참고 단가・이번 추가 비용・내부 예산 배정과 관측 범위를 설명한다. 사용량 예산은 실제 청구액과 구분한다. 공개 상태・사유・계획 계약은 유지한다.
- 수신 corpus와 배포된 정책 revision 1~3은 보존했다. `scripts/align_access_costs.py`가 회사 정책・가격・승인 경로・회수 규칙 revision 4 및 명시적인 비용 규칙・합성 라이선스 사실을 생성한다. DemoSeed는 누락된 revision 4를 자동 준비하며 현재 예산・기존 관측을 초기화하지 않는다.
- 현재 평가 원본은 `scenarios-current.json`이다. E-02는 기존 Notion 멤버의 편집 권한 추가(0원), P-05는 기존 Explorer의 프로젝트 권한 추가(0원)로 수정했다. 예산 부족은 Copilot 신규 구매 19 > 잔여 10의 BUDGET-INSUFFICIENT로 분리했다. full 33건・smoke 9건이며 재사용 사례는 가격을 0으로 조작하지 않고 조직 범위 라이선스 보유를 준비한다. 원래 v4는 비교 자료로 남긴다.
- 검증: Java `mvn -o ... test` **49 tests passed** (Mockito JVM 시작 agent 사용). 실제 planner의 8조건에는 참고 단가 20/70・예산 10・라이선스 보유 시 승인 대기와 plan 0원이 포함된다. Python Agent/MCP/live 검사 **232 passed, 1 skipped**, 평가 준비 오프라인 **6 tests passed**. 업무/HTTP 계약・정책 import・v4 및 비용 생성물 검사와 diff 공백 검사 통과. full 33건・smoke 9건 준비 확인.
- `AccessCostsIT`에 V10・policy revision 4 import/reapply, Notion/Tableau 승인 후 0원 실행, Copilot 예산 보류와 신규 구매 후 19달러 단일 차감・관측 갱신 검증을 추가했다. 테스트 소스는 컴파일됐으나 Docker 소켓 접근 거부로 실제 PostgreSQL/전체 HTTP 통합 실행은 미검증이다. Docker가 허용되는 환경에서 `cd backend && mvn verify -Pregression -Dit.test=AccessCostsIT` 또는 격리 smoke/full로 확인한다.
- 실행 중 DB에는 아직 적용하지 않았다. 새 backend/agent 이미지를 함께 빌드・기동해야 V10과 demo revision 4가 준비된다. 기존 승인 계획이 바뀐 비용 기준과 다르면 재분석・재승인이 필요하다.

## 비용 검토 지적 2건 보완 — 2026-10-23

- 비용 규칙 없는 유료 좌석・사용량 예산을 자동 승인 근거로 삼지 않도록 변경했다. 좌석 호환은 V9 기존 조직의 정책 revision 1과 이관 단가 출처에 한정하고, 새 정책은 명시적 규칙을 요구한다. PURCHASE_SEAT 규칙의 조직 범위・라이선스 코드가 없으면 BUDGET_UNAVAILABLE 수동 검토로 처리한다. 명시적인 0원 권한은 유지한다.
- 평가 준비 SQL에 구매 필요 여부・관측/만료 시각・관측 출처 유효성 검사를 추가했다. 실제 구매 필요가 false/null이거나 라이선스 관측이 누락・미래・만료이면 요청 전 PRECONDITION_FAILED로 분류한다. 시나리오/fixture에도 purchase_required 기대값을 명시했다.
- 관련 범위만 검증했다. Java AccessCostingTest・AccessPlanningReviewTest 9건, Python 평가 준비의 해당 회귀 검사 3건 통과. 비용 생성물 일치와 diff 공백 검사도 통과했다. 전체 테스트・Docker/LLM 통합 실행은 추가하지 않았다. migration・실행 중 DB・배포된 정책 본문은 변경하지 않았다.

### #56 최신 main 비용 변경 통합

PR 준비 중 main에 #47 비용 관리 및 V10__scoped_access_costs.sql이 병합됐다. 비용/평가 사전검사 변경을 유지해 병합하고 회수 신규 마이그레이션은 V11로 옮겼다. 구현 기록·시드 README의 양쪽 문서를 보존했다. 최종 계약 변경과 main 통합은 사용자 지시에 따라 실행 테스트를 추가하지 않은 상태다.

## 기본 시연 표시명 정리 — 2026-10-23 · #64

현재 단계: `fix/#64-seed-display-names`에서 구현·검증 완료. 사용자 확인 전이며 PR은 생성하지 않았다.

- 시드 생성기와 생성 SQL에서 회사·부서·TF·자원의 `Phase 2` 접두사를 제거했다. 예: `Phase 2 A사 업무팀` → `A사 업무팀`, `Phase 2 A GITHUB` → `A GITHUB`. 현재 기본 표시명에는 `Phase 1`이 없었다.
- 시드 재적용 때 고정 UUID·회사·원래 이름이 일치하는 기본 엔터티 30개의 표시명만 갱신한다. 사용자가 바꾼 이름과 LEGACY 조직, 계정·권한·예산·정책 원문/해시·과거 스냅샷/보고서·감사 기록을 보존한다. Flyway V1~V11 및 API·메시지 계약은 변경하지 않았다.
- 평가 fixture가 이름의 `Phase 2` 접두사로 회사별 구분자를 붙이던 부분도 새 이름에 맞췄다. full 33개 사례의 부서명 66개가 고유하게 유지된다.
- `SeedDisplayNamesIT`는 신규 시드·로그인 프로필 부서명과 기존 이름 재적용, 사용자 변경 이름·ID·업무 상태·불변 이력 보존 및 멱등성을 일회용 PostgreSQL에서 검증한다. 원본에서 `A사 (mock)` 기대에 `Phase 2 A사 (mock)`가 반환돼 실패한 뒤 수정본에서 통과했다.

실제 검증 결과:

- 변경 전 단위 51개와 기존 PostgreSQL/브로커 회귀 3개 통과. 최초 기본 `mvn test`는 로컬 Mockito 동적 부착 제한으로 28개 오류가 발생했고, JVM 시작 시 Mockito javaagent를 지정한 동일 검사에서 통과했다.
- 변경 후 `mvn verify -Pregression`에 Mockito javaagent와 Docker API 1.44 옵션을 사용해 단위 51개·DB/브로커 통합 20개 통과(실패·오류·건너뜀 0).
- 평가 준비 `PYTHONPATH=scripts/phase2 /private/tmp/unlockops-56-venv/bin/python -m unittest test_evaluation` 9개 통과. 이름 중복 회귀는 수정 전 66개 중 고유 이름이 2개여서 실패한 뒤 수정 후 통과했다. 시스템 Python에는 httpx가 없어 기존 임시 가상환경을 사용했다.
- 생성기 재실행으로 SQL·catalog·회사별 정책 원문 4개 생성물의 바이트 일치를 확인했다. catalog와 정책 원문은 변경되지 않았다. `git diff --check` 통과.
- 실행 중 개발 DB·컨테이너는 변경하지 않았다. 브라우저 화면·Python Worker/MCP 전체 스택은 미검증이며, 기존 실행 DB의 V10 번호 충돌 복구는 이번 표시명 변경에 포함하지 않는다.

적용: Flyway가 정상 완료되는 시연 DB에서 수정된 seed를 재적용하거나 `DEMO_SEED_PATH`를 사용하는 백엔드를 재시작한다. 프론트/API 필드 변경 없이 다음 프로필·목록 조회에서 새 이름을 받는다. 로그인된 화면은 새로고침 또는 재로그인으로 프로필을 다시 가져올 수 있다.

### #64 후속: seed.sql의 잔여 개발 단계 표기 제거

사용자의 추가 요청에 따라 현재 엔터티 이름에서 신규 baseline 정책 제목·합성 과거 스냅샷까지 정리 범위를 확장했다. `seed.sql`의 `Phase 1`·`Phase 2` 리터럴은 0건이다. 이전 기록의 정책 생성물 보존 방침 중 신규 baseline 제목은 이번 요청에 따라 변경했으며, 기존 DB의 불변 정책·이력 보존은 유지한다.

- 기본 정책 원문 제목과 SHA-256, 합성 스냅샷 자원 이름을 생성기와 함께 수정했다. 계약 예시 3개 파일은 해당 정책 해시만 갱신하고 기존 검증 사례를 보존했다.
- 기존 기본 이름은 개발 단계 접두사를 처리하는 정규식과 UUID·회사·정리 후 이름을 함께 확인해 갱신한다. 사용자 수정 이름은 보존한다.
- 기존 DB의 revision 1을 덮어쓰지 않는다. R-04 과거 이력이 누락돼 새로 추가할 때는 DB에 실제 설치된 정책 원문과 해시를 스냅샷·후보·보고서 근거에 일관되게 사용한다.
- revision 2 가져오기 생성기/SQL의 baseline 검증은 제목 정리 전·후의 알려진 해시만 허용한다. revision 2~4의 정책 원문·해시와 Flyway V1~V11은 변경하지 않았다.
- 신규 회귀는 잔여 문자열 때문에 원본에서 실패한 뒤 수정본에서 통과했다. 후속 정책 가져오기의 기존 baseline 해시 조건으로 발생한 통합 실패도 수정했다. 기존 제목의 정책만 설치된 DB에서 누락 이력 보완·revision 2~4 적용·재적용 보존을 일회용 PostgreSQL로 확인했다.
- 검증: `mvn verify -Pregression` (Mockito javaagent, Docker API 1.44) 단위 51개·DB/브로커 통합 21개 통과. 계약 예시 해시 갱신 후 Java WorkflowContractTest 2개 추가 확인, Python 업무 계약·정책 import·평가 준비 63개와 subtest 7개 통과. 실패·오류·건너뜀 없음.
- seed 생성물 4개 재생성 바이트 일치, 정책 import 생성물 `--check`, 잔여 리터럴 0건 및 diff 공백 검사 통과. 개발 DB 미적용이며 브라우저·Worker/MCP 전체 스택은 미검증이다.

## README 서비스·Agent 설계·시각 구성 개편 — 2026-10-26 · #68

현재 단계: 문서·이미지 개편과 정적 검증 완료. 커밋·푸시·PR 생성은 수행하지 않았다.

- 서비스 소개를 요청·승인과 미사용 유료 좌석 회수의 흐름으로 정리하고, 제공된 발표자료의 실제 시연 화면을 포함했다. 승인 분석·승인 후 실행·회수 점검의 실제 노드, 시스템 아키텍처와 RAG를 Mermaid 5개로 설명한다.
- RAG의 회사/정책 revision 범위·원문 인용 검증, MCP 9개 도구와 실행 입력 제한, 하네스의 호출 한도·승인 계획 검증·독립 재조회·Outbox/Inbox·체크포인트 복구를 코드에 대조해 정리했다. 승인과 회수의 사실 조회 시점·최종 상태 책임을 구분한다.
- 발표자료 20번째 슬라이드의 캐릭터 장면, 표지의 투명 배경 캐릭터, 기술 스택 아키텍처를 원본 그대로 추출했다. 상단 브랜드·기술 배지·바로가기와 팀 프로필 표를 추가했다. 공개 GitHub 계정과 git author/담당 영역을 대조해 아바타·계정 링크를 연결했다.
- 제공된 검증결과서·발표자료의 20문항 비교 실험은 `docs/evaluation.md`에 조건·출처·원시 결과 미추적·단회 비교의 한계와 함께 정리했다. 이번 문서 작업에서 모델 평가를 재실행한 결과가 아니다.
- GitHub가 우선 표시하던 오래된 `.github/README.md` 중복을 제거해 루트 README를 기준으로 통일하고, CONTRIBUTING의 협업 설정 링크를 `.github/GITHUB_SETUP.md`로 수정했다.
- 검증: 원본 이미지 바이트 일치, Mermaid 코드 블록 5개와 실제 그래프 노드명 대조, Markdown 파싱 및 6인 프로필 표 구조, 로컬 참조 90개와 기술 섹션 앵커, 외부 배지·아바타 이미지 26개 HTTP 200/image 확인, `git diff --check` 통과. 문서 변경으로 애플리케이션·LLM·전체 스택 실행 테스트는 추가하지 않았다. GitHub 웹 화면의 실제 렌더링은 별도 확인하지 않았다.

다음 작업: 팀원 검토 후 문서 변경을 커밋·푸시한다. 기능 변경 시 README의 그래프·계약 설명과 연결된 상세 문서를 함께 갱신한다.

### README 문장과 마지막 이미지 배치 보완

- 사용자 요청에 따라 기존의 좌측 로고와 설명, 우측 캐릭터 헤더를 유지했다. 마지막 이미지는 팀 소개 뒤 문서 끝에 폭 960으로 배치하고 여백과 구분선으로 마무리했다. 자료 링크는 팀 소개 앞으로 옮겼으며 이미지 원본은 수정하지 않았다.
- README에 있던 가운데점 252개를 제거했다. 명사 나열은 문장으로 풀고 그래프 설명은 줄바꿈으로 정리했다. 팀 역할과 안내 문구도 같은 기준으로 다듬었다.
- 검증: Mermaid 5개의 라벨을 제외한 구조가 수정 전과 같고, 팀 프로필 6개도 유지된다. 본문 가운데점 0개, 로컬 링크와 앵커 63개 연결, Markdown과 6인 팀 표 파싱, `git diff --check`를 확인했다. 문서 편집이므로 애플리케이션 실행 테스트는 추가하지 않았다.

### README 최종 순서 조정

- 사용자 요청으로 `평가와 개선`, `현재 범위와 다음 단계` 섹션을 본문에서 삭제했다. 상세 평가 문서는 자료 링크로 유지한다.
- 팀 소개를 변혜민, 임채환, 김지성, 김동빈, 김민지, 신형철 순으로 재배치했다. 사진과 GitHub 계정, 담당 역할도 같은 순서로 옮겼다.
- 마지막 이미지를 폭 520으로 줄이고 팀의 짧은 마무리 문구를 붙였다. `코드와 상세 문서`는 이미지와 문구 다음의 최하단으로 이동했다. 헤더와 기술 그래프는 변경하지 않았다.
- 검증: 헤더와 Mermaid 5개가 수정 전과 동일하고 팀원별 이름과 아바타 순서가 일치한다. Markdown 파싱, 본문 가운데점 0개, 로컬 참조와 앵커 62개, `git diff --check`를 확인했다.

### 시연 플랫폼 로고 표시

- 시연 대상의 텍스트 나열을 로고와 이름이 있는 5열 2행 표로 변경했다. 프론트에서 사용하는 컬러 로고 원본 10개를 재사용하고 표시 폭을 40으로 맞췄다.
- 10개 이미지 경로, 대체 텍스트, 표의 행과 열 구조, 기존 Mermaid 5개와 최하단 문서 배치를 확인했다. `git diff --check`를 통과했다.
- 사용자 요청으로 플랫폼 로고 10개의 표시 폭을 40에서 24로 줄였다. 다른 이미지 크기와 배치는 유지하고 공백 검사를 통과했다.

### 마지막 이미지 위치와 크기 조정

- 최신 요청에 따라 마무리 이미지를 상세 문서보다 뒤인 문서 맨 끝으로 이동했다. 표시 폭을 520에서 360으로 줄이고, 중앙 정렬한 이미지 아래에 UnlockOps와 Team Bana100을 배치했다.
- 헤더와 기술 그래프는 그대로 유지했다. 이미지가 한 번만 사용되고 문서 최하단에 있는지, Mermaid 5개와 헤더가 수정 전과 동일한지 확인했다. `git diff --check`를 통과했다.
