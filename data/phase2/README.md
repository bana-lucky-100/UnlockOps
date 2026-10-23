# Phase 2 mock 데이터

**실제 가격/회사 정책이 아닌 baseline-v1 합성 데이터**다. 고정 기준 시각은 2026-10-22 09:00 Asia/Seoul.
기존 활성 `data/policy_corpus.md`, 권한표, 기존 사용자·권한·예산을 변경하지 않는다.
실제 참조 문서는 전체 베이스라인을 구현한 뒤 교체한다. 이후 교체도 새 revision으로 저장한다.

현재 v4 적용 절차는 [policies/README.md](policies/README.md)에 있습니다. 아래 seed는 revision 1 기준선이며, 수신 RAG revision 2와 v4 정합화 revision 3을 순서대로 추가합니다.

## 파일

| 파일 | 용도 |
|---|---|
| catalog.json | A/B 회사·직원·자원·권한·가격의 안정적인 UUID, 평가셋 20건의 조건/기대값 |
| seed.sql | 신규 테이블에 넣는 opt-in mock 데이터. 트랜잭션으로 적용, 재실행 시 기존 레코드 보존 |
| company-a-policy.md | 임시 정책 및 부서장→IT 담당자 2단계 승인 |
| company-b-policy.md | 임시 정책 및 팀장→부서장→SaaS 담당자, 100 USD 이상 IT 총괄 추가 |

원본 생성기는 `scripts/generate_phase2_seed.py`다. 파일 셋 변경은 생성기를 수정한 뒤 다시 생성한다.
가격은 catalog의 구조화된 decimal 문자열을 사용하고, 정책은 doc/source hash로 연결한다.
`source_kind=SYNTHETIC_CONTRACT`로 실제 공식 가격과 구분한다. USAGE_ESTIMATE는 실제 청구액이 아니다.

## 안전한 적용

Compose 시연 환경은 `DEMO_ENABLED=true`와 `DEMO_PHASE2_SEED_PATH=/app/data/phase2/seed.sql`을 사용한다.
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

## 재현 범위

- A/B 각각 10개 SaaS 자원·권한·가격과 플랫폼별 담당자 매핑.
- 별도의 GitHub 저장소 Read/Write 항목·팀, Jira Developer의 Browse 스킴을 보존할 데이터.
- 현재 계정/라이선스/데이터 접근/업무 배정 전제는 saas_context_facts의 합성 사실이다. 외부 계정 연동이 아니다.
- R-01~R-04, 퇴사자 X-11, 사용 이력 UNKNOWN은 각각 다른 사용자와 할당을 사용한다.
- R-04는 이미 전달된 인앱 알림을 포함한다. 정상 신규 점검 결과나 권한 실행 영수증을 미리 만드는 것은 아니다.
- A사 기본 scope는 R-01 한 건, B사 기본 scope는 X-10 GitHub/Figma 두 건이다. R-02/R-03/R-04/X-11/UNKNOWN은 별도 scope_id로 격리한다.
- selection_mode=ASSIGNMENTS는 서버에 저장된 scope→assignment 목록으로 제한한다. DEPARTMENT 범위는 해당 조직 전체를 조회한다. 클라이언트가 임의 할당 목록을 전달하지 않는다.
- 평가셋 20개의 budget/membership/decision 등 overrides는 **개별 평가에서 적용할 데이터 정의**다. 현재 서비스 동작을 의미하지 않는다.
- execution_ready=true는 평가 실행기가 해당 조건을 적용할 수 있다는 뜻이다. 통과 표시는 아니며 원본의 validation_status는 NOT_RUN이다. 실제 결과는 실행별 report.json에만 남긴다.

## 격리 평가 실행

```sh
python3 scripts/evaluate_phase2.py --plan --suite full
python3 scripts/evaluate_phase2.py --run --suite smoke
python3 scripts/evaluate_phase2.py --run --suite full
```

기본은 데이터 준비만 수행한다. `--run`은 별도 Docker 프로젝트/DB/큐/체크포인트를 만들고 종료 시 해당 프로젝트만 정리한다.
평가마다, 그리고 시나리오마다 회사·사용자·자원을 복사하며 고정 기준일을 실행일로 이동한다.
기존 시연 DB에 overrides를 덮어쓰지 않는다. full은 원본 20건과 플랫폼별 담당자·미조회·4단계 승인·퇴사자·비용 UNKNOWN 5건, 총 25건이다.
결과는 `test-results/phase2/<run_id>/report.json`에 남긴다. Docker/설치 실패는 BLOCKED, 미실행 사례는 NOT_RUN이며 성공으로 집계하지 않는다.
화면 클릭·모바일·세션 만료는 별도 수동 확인 대상으로 남으며 자동 API 평가와 구분한다. 세부 시연 순서는 루트 `IMPLEMENTATION.md`를 참고한다.

기존 permissions/GitHub 팀/Jira 스킴은 v1의 현재 데이터 원천이다. access_assignments에는 v2 mock만 넣는다.
v1 데이터를 조용히 복사해 최신 할당처럼 읽는 방식은 사용하지 않는다. 실제 전환 시 잠금·이관·단일 writer를 2단계에서 구현한다.

## v4 시나리오 실행 기준

기존 `catalog.json`·`seed.sql`은 baseline-v1 이력으로 보존한다. 현재 평가 기준은 `scenarios-v4.json`이며, seed 이후 `policies/apply.sql`(revision 2), `policies/apply-v4.sql`(revision 3)을 적용한다. Figma 16달러와 최신 근거·Run as 사실은 revision 3 적용 기준이다. 실행 절차는 [정책 적용 안내](policies/README.md#최종-시나리오-v4-적용-앞선-revision-2-설명-이후)를 따른다.

평가 full은 핵심 20건 + 추가 9건이다. X-UNKNOWN→X-08b-USAGE, X-COST→X-08b-COST, X-4STEP→X-03으로 맞췄으며 X-07(입력 마스킹), X-08(후보·추가 확인 없음), X-12(첫 플랫폼만 처리), X-06(담당자 부재)을 추가했다. X-01/X-02는 P-01/P-06, X-04는 정상 승인 후 검증 단계에서 함께 확인한다. X-05는 에이전트 검증 실패 회귀 검사, X-09의 불완전 조회는 회수 그래프 회귀 검사로 확인한다. X-10 외부 알림 실패의 실환경 장애 주입은 통합 실행에서 별도 확인해야 한다. 케이스별 검증 위치는 아래 대응표에 정리했다.

## 시나리오 X ID ↔ 테스트 이름 대응표

평가 실행기에 별도 케이스가 없던 X-04·X-05·X-06·X-09의 검증 위치다. 저장소에서 확인한 테스트만 적는다.

| 시나리오 ID | 기대 상태·사유 | 검증하는 곳 | 비고 |
|---|---|---|---|
| X-04 | DONE / VERIFIED | `agent/tests/test_phase2_workflows.py::test_execution_requires_fresh_verification_and_preserves_mismatch`(verified=True → DONE, `verification_ok=True`), 평가 실행기 승인 완료 케이스의 독립 검증(`scripts/phase2/run_suite.py:152`, DONE·ACCESS_VERIFIED·`verification_ok=True`) | 별도 평가 케이스 없음. E-01·P-01~P-06·B-02·X-03·X-07·X-12가 승인 후 이 검증을 통과해야 PASS |
| X-05 | FAILED / VERIFICATION_FAILED | `agent/tests/test_phase2_workflows.py::test_execution_requires_fresh_verification_and_preserves_mismatch`(verified=False → FAILED, `verification_ok=False`) | 사유 코드 문자열은 v1 그래프 테스트(`agent/tests/test_scenarios.py::test_verification_retry_policy_never_reexecutes_grant`)에서만 확인됨. 평가 실행기에는 검증 단계 실패 주입이 필요해 없음 |
| X-06 | MANUAL_REVIEW / APPROVER_UNAVAILABLE | 평가 실행기 케이스 `X-06`(`scripts/phase2/fixtures.py` EXTRA) | 격리 회사 복사본에서 A사 담당자(operator)를 `employment_status='LEFT'`로 바꿔 승인자를 지정할 수 없게 함. 분석 단계에서 MANUAL_REVIEW로 끝나 승인·실행·예산 차감이 없어야 함 |
| X-09 | FAILED / SCAN_FAILED | `agent/tests/test_phase2_workflows.py::test_reclaim_requires_all_unique_rows_and_never_claims_done`(중복 행 → FAILED, `scan_complete=False`) | 서버가 사유 코드를 SCAN_FAILED로 기록하는 부분(`ReclaimResultService`)은 테스트 없음. 시나리오의 불완전 조회 조건은 데이터만으로 재현 불가라 평가 실행기에 없음 |
