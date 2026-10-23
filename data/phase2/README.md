# Phase 2 mock 데이터

현재 Compose 시연 시작은 baseline과 누락된 정책 revision 2·3·4을 한 트랜잭션으로 준비한다. 아래 파일 경로와 baseline은 비교·이력 보존용이며 별도 실행기를 뜻하지 않는다. 수동 SQL 적용도 계속 지원한다.

**실제 가격/회사 정책이 아닌 baseline-v1 합성 데이터**다. 고정 기준 시각은 2026-10-22 09:00 Asia/Seoul.
기존 활성 `data/policy_corpus.md`, 권한표, 기존 사용자·권한·예산을 변경하지 않는다.
실제 참조 문서는 전체 베이스라인을 구현한 뒤 교체한다. 이후 교체도 새 revision으로 저장한다.

현재 v4 적용 절차는 [policies/README.md](policies/README.md)에 있습니다. 아래 seed는 revision 1 기준선이며, 수신 RAG revision 2와 v4 정합화 revision 3, 비용 정합화 revision 4를 순서대로 추가합니다.

## 파일

| 파일 | 용도 |
|---|---|
| catalog.json | A/B 회사·직원·자원·권한·가격의 안정적인 UUID, 평가셋 20건의 조건/기대값 |
| seed.sql | 신규 테이블에 넣는 opt-in mock 데이터. 트랜잭션으로 적용, 재실행 시 원래 시연 표시명만 정리하고 업무 상태 보존 |
| company-a-policy.md | 임시 정책 및 부서장→IT 담당자 2단계 승인 |
| company-b-policy.md | 임시 정책 및 팀장→부서장→SaaS 담당자, 100 USD 이상 IT 총괄 추가 |

원본 생성기는 `scripts/generate_phase2_seed.py`다. 파일 셋 변경은 생성기를 수정한 뒤 다시 생성한다.
가격은 catalog의 구조화된 decimal 문자열을 사용하고, 정책은 doc/source hash로 연결한다.
`source_kind=SYNTHETIC_CONTRACT`로 실제 공식 가격과 구분한다. USAGE_ESTIMATE는 실제 청구액이 아니다.

## 안전한 적용

Compose 시연 환경은 `DEMO_ENABLED=true`와 `DEMO_SEED_PATH=/app/data/phase2/seed.sql`을 사용한다.
backend는 Flyway 마이그레이션 후 seed와 계정 비밀번호 준비를 한 트랜잭션으로 수행한다. 기존 행은 보존하고,
지정된 A/B사 합성 시연 계정 12개의 비밀번호만 현재 DEMO_PASSWORD에 맞춘다. 재시작할 때 요청·승인·예산을 초기화하지 않는다.
카드 또는 담당 역할을 선택하면 비밀번호 입력 없이 바로 로그인한다. 빠른 로그인은 시연 모드와 지정된 mock 계정에서만 가능하다.

개별 백엔드 실행에서는 두 설정을 명시하거나 신규 V7까지 마이그레이션을 적용한 **로컬/시연 DB**에 아래처럼 수동 적용한다.
DEMO_ENABLED=false이거나 DEMO_PHASE2_SEED_PATH가 비어 있으면 seed를 자동 실행하지 않는다.

```sh
# 기존 compose 시연 DB를 사용하며 해당 backend에 V7까지 먼저 적용돼 있어야 한다.
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/seed.sql
```

다른 환경은 해당 환경의 접속 설정으로 `psql -v ON_ERROR_STOP=1 -f data/phase2/seed.sql`을 실행한다.
새 시연 계정은 p2_a_/p2_b_ 접두사를 쓰며 비밀번호 해시를 seed에 넣지 않는다.
DEMO_ENABLED=true와 DEMO_PASSWORD 설정으로 backend를 재시작하면 DemoSeed가 비어 있는 해시와 지정된 mock 시연 계정의 비밀번호를 준비한다.
새 계정·플랫폼은 `/access` 및 v2 업무 API에서 시연한다.
회수 scopes.enabled=false로 시작하므로 이후 Scheduler를 붙여도 운영자가 범위를 확인해 활성화해야 한다.

## 기본 시연 표시명

현재 회사·부서·TF·자원 표시명에는 개발 단계 접두사를 넣지 않는다. 예를 들어 `Phase 2 A사 업무팀`은 `A사 업무팀`, `Phase 2 A GITHUB`는 `A GITHUB`로 준비한다. 생성기와 `seed.sql`을 함께 관리한다.

기존 DB는 위 시드 재적용 명령이나 `DEMO_SEED_PATH`를 사용하는 백엔드 재시작으로 반영한다. 고정 시드 UUID·회사와 원래 표시명이 모두 일치하는 30개 엔터티만 이름을 바꾸며, 사용자가 수정한 이름은 유지한다. 계정·식별자·권한·예산·정책 원문과 해시·과거 회수 스냅샷은 보존한다. 과거 스냅샷의 이름은 당시 사실이므로 그대로 남긴다.

시드 적용은 Flyway가 정상 완료된 로컬/시연 DB를 전제로 한다. 이 표시명 변경은 기존 DB의 마이그레이션 번호·체크섬 충돌을 복구하지 않는다.

회귀 검증은 `cd backend && mvn verify -Pregression -Dit.test=SeedDisplayNamesIT,WorkflowFoundationIT,ReclaimSeedReportIT`로 실행한다. 신규 표시명과 로그인 프로필 부서명, 기존 기본 이름 갱신, 사용자 수정 이름·업무 상태·불변 이력 보존과 재적용 멱등성을 일회용 PostgreSQL에서 확인한다.

## 재현 범위

- A/B 각각 10개 SaaS 자원·권한·가격과 플랫폼별 담당자 매핑.
- 별도의 GitHub 저장소 Read/Write 항목·팀, Jira Developer의 Browse 스킴을 보존할 데이터.
- 현재 계정/라이선스/데이터 접근/업무 배정 전제는 saas_context_facts의 합성 사실이다. 외부 계정 연동이 아니다.
- R-01~R-04, 퇴사자 X-11, 사용 이력 UNKNOWN은 각각 다른 사용자와 할당을 사용한다.
- R-04는 이미 전달된 인앱 알림과 그 알림이 여는 **합성 과거 점검·스냅샷·보고서**를 함께 포함한다. 과거 시점은 2026-10-21 09:00 KST, 정책은 revision 1, 좌석은 월 19 USD다. 새 점검을 시작하기 전에도 알림에서 후보 상세와 근거를 읽을 수 있다. 현재 점검의 성공 결과나 권한 실행 영수증을 미리 만드는 것은 아니다.
- A사 기본 scope는 R-01 한 건, B사 기본 scope는 X-10 GitHub/Figma 두 건이다. R-02/R-03/R-04/X-11/UNKNOWN은 별도 scope_id로 격리한다.
- selection_mode=ASSIGNMENTS는 서버에 저장된 scope→assignment 목록으로 제한한다. DEPARTMENT 범위는 해당 조직 전체를 조회한다. 클라이언트가 임의 할당 목록을 전달하지 않는다.
- 평가셋 20개의 budget/membership/decision 등 overrides는 **개별 평가에서 적용할 데이터 정의**다. 현재 서비스 동작을 의미하지 않는다.
- execution_ready=true는 평가 실행기가 해당 조건을 적용할 수 있다는 뜻이다. 통과 표시는 아니며 원본의 validation_status는 NOT_RUN이다. 실제 결과는 실행별 report.json에만 남긴다.

## 기존 R-04 알림의 보고서 누락 보완

기존 시드는 후보와 전달된 알림만 만들었기 때문에, 새 점검 전 후보 상세 API가 404를 반환하고 현재 후보 목록에서 빠질 수 있었다. 수정된 `seed.sql`을 기존 시연 DB에 다시 적용하거나 `DEMO_SEED_PATH`를 사용하는 백엔드를 재시작하면 누락된 합성 과거 이력이 추가된다. 자동 시드가 아닌 환경의 재적용 명령은 위의 시드 적용 명령과 같다.

이 재적용은 기존 후보·episode·알림 ID, 전달/읽음 시각, 이미 저장된 보고서·스냅샷과 정책 revision 2·3을 덮어쓰지 않는다. 권한·예산도 변경하지 않는다. 이미 revision 3을 사용한다면 과거 `policies/apply.sql`을 다시 적용할 필요가 없다. 당시 revision 1 근거는 과거 보고서에 보존하고, 새 점검만 최신 정책을 따른다.

회귀 검증은 `cd backend && mvn verify -Pregression -Dit.test=ReclaimSeedReportIT,WorkflowFoundationIT`로 실행한다. 격리 smoke의 R-04도 새 점검 전 알림 상세와 overview를 먼저 검사한 뒤 재점검/중복 알림 방지를 확인한다.

## 격리 평가 실행

```sh
python3 scripts/evaluate_phase2.py --plan --suite full
python3 scripts/evaluate_phase2.py --run --suite smoke
python3 scripts/evaluate_phase2.py --run --suite full
```

기본은 데이터 준비만 수행한다. `--run`은 별도 Docker 프로젝트/DB/큐/체크포인트를 만들고 종료 시 해당 프로젝트만 정리한다.
평가마다, 그리고 시나리오마다 회사·사용자·자원을 복사하며 고정 기준일을 실행일로 이동한다.
기존 시연 DB에 overrides를 덮어쓰지 않는다. full은 핵심 20건 + 추가 9건 + 비용 경계 4건, 총 33건이며 smoke는 9건이다.
결과는 `test-results/phase2/<run_id>/report.json`에 남긴다. Docker/설치 실패는 BLOCKED, 미실행 사례는 NOT_RUN이며 성공으로 집계하지 않는다.
화면 클릭·모바일·세션 만료는 별도 수동 확인 대상으로 남으며 자동 API 평가와 구분한다. 세부 시연 순서는 루트 `IMPLEMENTATION.md`를 참고한다.

현재 신규 쓰기는 access_assignments와 모의 제공자 상태를 사용한다. 기존 permissions/GitHub 팀/Jira 스킴은 과거 데이터로 보존하며 새 할당으로 자동 복사하지 않는다. 구 실행기는 제거했다.

## v4 시나리오 실행 기준

기존 `catalog.json`·`seed.sql`은 baseline-v1 이력으로 보존한다. 변경 전 v4 비교 기준은 `scenarios-v4.json`이며, seed 이후 `policies/apply.sql`(revision 2), `policies/apply-v4.sql`(revision 3)을 적용한다. Figma 16달러와 최신 근거·Run as 사실은 revision 3 적용 기준이다. 실행 절차는 [정책 적용 안내](policies/README.md#최종-시나리오-v4-적용-앞선-revision-2-설명-이후)를 따른다.

현재 평가는 `scenarios-current.json`(정책 revision 4)을 사용하며 full은 핵심 20건 + 추가 9건 + 비용 경계 4건이다. X-UNKNOWN→X-08b-USAGE, X-COST→X-08b-COST, X-4STEP→X-03으로 맞췄으며 X-07(입력 마스킹), X-08(후보·추가 확인 없음), X-12(첫 플랫폼만 처리), X-06(담당자 부재)을 추가했다. X-01/X-02는 P-01/P-06, X-04는 정상 승인 후 검증 단계에서 함께 확인한다. X-05는 에이전트 검증 실패 회귀 검사, X-09의 불완전 조회는 회수 그래프 회귀 검사로 확인한다. X-10 외부 알림 실패의 실환경 장애 주입은 통합 실행에서 별도 확인해야 한다. 케이스별 검증 위치는 아래 대응표에 정리했다.

## 시나리오 X ID ↔ 테스트 이름 대응표

평가 실행기에 별도 케이스가 없던 X-04·X-05·X-06·X-09의 검증 위치다. 저장소에서 확인한 테스트만 적는다.

| 시나리오 ID | 기대 상태·사유 | 검증하는 곳 | 비고 |
|---|---|---|---|
| X-04 | DONE / VERIFIED | `agent/tests/test_phase2_workflows.py::test_execution_requires_fresh_verification_and_preserves_mismatch`(verified=True → DONE, `verification_ok=True`), 평가 실행기 승인 완료 케이스의 독립 검증(`scripts/phase2/run_suite.py:152`, DONE·ACCESS_VERIFIED·`verification_ok=True`) | 별도 평가 케이스 없음. E-01·P-01~P-06·B-02·X-03·X-07·X-12가 승인 후 이 검증을 통과해야 PASS |
| X-05 | FAILED / VERIFICATION_FAILED | `agent/tests/test_phase2_workflows.py::test_execution_requires_fresh_verification_and_preserves_mismatch`(verified=False → FAILED, `verification_ok=False`) | 사유 코드 문자열은 v1 그래프 테스트(`agent/tests/test_scenarios.py::test_verification_retry_policy_never_reexecutes_grant`)에서만 확인됨. 평가 실행기에는 검증 단계 실패 주입이 필요해 없음 |
| X-06 | MANUAL_REVIEW / APPROVER_UNAVAILABLE | 평가 실행기 케이스 `X-06`(`scripts/phase2/fixtures.py` EXTRA) | 격리 회사 복사본에서 A사 담당자(operator)를 `employment_status='LEFT'`로 바꿔 승인자를 지정할 수 없게 함. 분석 단계에서 MANUAL_REVIEW로 끝나 승인·실행·예산 차감이 없어야 함 |
| X-09 | FAILED / SCAN_FAILED | `agent/tests/test_phase2_workflows.py::test_reclaim_requires_all_unique_rows_and_never_claims_done`(중복 행 → FAILED, `scan_complete=False`) | 서버가 사유 코드를 SCAN_FAILED로 기록하는 부분(`ReclaimResultService`)은 테스트 없음. 시나리오의 불완전 조회 조건은 데이터만으로 재현 불가라 평가 실행기에 없음 |

## 담당자 확정 모의 회수

점검 시나리오는 기존처럼 후보·보고서·알림을 생성합니다. 추가된 모의 회수 API는 담당자가 확정한 ACTIVE SEAT를 종료하고 완료 영수증을 저장합니다. 시드만 준비된 할당은 mock_entitlement_memberships가 없을 수 있으므로 영수증의 provider_present_before=false도 정상이며, 실제 부여로 멤버십이 존재하는 경로는 별도 DB 통합 테스트로 검증합니다.

회수 후 시드를 재적용해도 INACTIVE 할당·회수 영수증·종결된 후보는 보존합니다. 실행 중인 개발 DB의 회수 사례를 재현하려고 시드를 무단 초기화하지 않습니다. API와 상태 계약은 [전달 문서](../../docs/reclaim-execution-api.md)를 따릅니다.

## 승인 판단 조건과 준비 검증

현재 비용 기준은 `scenarios-current.json`이며 `scripts/align_access_costs.py`가 revision 3 비교 자료에서 생성한다. 기존 baseline과 정책 revision을 덮어쓰지 않는다. V10 migration 후 `policies/apply-costs.sql`이 정책・가격・경로・회수 규칙 revision 4와 비용 규칙・대상 조직의 라이선스 관측을 추가한다. Compose 시연은 누락된 revision 4를 자동 준비한다.

Notion E-02・Tableau P-05는 기존 라이선스로 가능한 권한 추가이며 추가 비용 0이다. 가격표의 20・70달러는 참고 단가로 남긴다. `BUDGET-INSUFFICIENT`는 Copilot 신규 구매 19 > 잔여 10으로 예산 보류를 검증한다. 경계 4건은 부족・일치・충분・기존 좌석 재사용이다. 기존 좌석 재사용은 Copilot 라이선스 관측을 COVERED로 준비하며 가짜 가격 0원을 삽입하지 않는다.

`preconditions`・`decision_rule`・기대 상태를 분리한다. `--run`은 요청 접수 전에 실제 DB의 가격・비용 규칙・조직 범위의 라이선스・예산 조건을 검사한다. 다르면 해당 건은 `PRECONDITION_FAILED`, 전체는 `BLOCKED`로 중단한다. 나머지 요청은 실행하지 않는다. `--plan`은 DB 검증을 하지 않으며 상태는 `NOT_RUN`이다. 세부 조건과 결과 해석은 [승인 판단 조건](../../docs/approval-decision-conditions.md)을 따른다.
