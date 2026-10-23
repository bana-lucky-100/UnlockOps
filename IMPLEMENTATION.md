# UnlockOps 구현 기록

이 파일은 팀이 구현 내용과 설계 의도를 함께 확인하는 **누적 기록의 기준 파일**입니다.
이후 작업도 새 정리 파일을 만들지 않고 이 파일의 현재 상태와 작업 이력을 갱신합니다.

- 위치: 바탕화면 `UnlockOps/IMPLEMENTATION.md`
- 기준일: 2026-10-22
- 현재 범위: **Phase 2 베이스라인 5단계 — 격리 평가 실행기·전체 시나리오·시연 검증 절차**
- 실제 권한 말소, 외부 SaaS 호출, 실제 가격 적용은 이번 범위가 아닙니다.

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

## 다음 작업

1. Docker 및 패키지 다운로드가 가능한 환경에서 smoke → full을 실행하고 FAIL/BLOCKED를 해결합니다. 수동 GitHub workflow로도 실행할 수 있습니다.
2. 위 브라우저 시연 항목과 기존 데이터 복제본의 V5→V7 업그레이드를 확인합니다.
3. 기준 결과를 확보한 뒤 실제 RAG 문서·가격을 새 revision으로 추가하고 같은 평가를 다시 실행해 변화와 에이전트 품질을 비교합니다.

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
