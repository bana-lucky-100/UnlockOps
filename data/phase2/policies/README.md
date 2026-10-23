# 수신 RAG 문서 반영 · 2026-10-23

`policy_corpus.md`는 제공받은 원문을 그대로 보관한 파일이다. 사내 규정 POL-01~14와 공식 요약 14건, 총 28개 문서·107개 조항/요약 청크를 포함한다. 공식 링크·확인일·정가는 제공 문서의 기록이며 이번 반영에서 웹 원문을 재검증하지 않았다.

기존 `data/policy_corpus.md`는 단일 승인 v1에서 사용한다. 새 문서의 순차 승인·Admin 최소 권한 제안과 v1 규칙이 다르므로 v1 원문을 덮어쓰지 않는다. 새 자료는 Phase 2 회사별 정책 revision 2로 연결한다.

## 검색에 반영하는 방식

- `scripts/import_phase2_policy.py`가 원문 표의 문서 ID·플랫폼·버전/확인일을 읽고, 규정은 조항별, 공식 요약은 요약·진단 힌트·원문별로 나눈다.
- 각 청크 제목은 `POL-14 | FIGMA | v1.0 | 제3조(좌석 비용)`처럼 고유하다. 여러 문서의 `핵심 요약` 제목이 겹쳐 근거가 덮이는 것을 방지한다.
- 회사별 승인 경로와 현재 구현 범위를 덧붙인 `company-a-policy-v2.md`, `company-b-policy-v2.md`를 생성한다. 원문 파일은 수정하지 않는다.
- DB의 `doc_id=P2-A-POLICY/P2-B-POLICY`, `revision=2`, 전체 묶음 해시를 근거에 유지한다. 개별 문서 ID·원문 버전은 article에 유지한다. 정책 묶음 버전 2와 개별 규정 v1.0/v1.1은 다르다.
- 승인 요청은 서버에서 조회한 플랫폼과 COMMON 청크만 검색·원문 조회한다. 회수는 고정 스냅샷에 연결된 정책 묶음을 사용한다. 다른 회사 정책이나 최신 정책으로 임의 교체하지 않는다.
- 임베딩 설정 없이 기존 TF-IDF 검색으로 동작한다. 새 해시·본문·플랫폼은 다른 캐시 항목을 사용한다.

## DB 적용

생성기는 SQL 파일만 만들며 DB에 자동 접속하지 않는다. 기존 V1~V7 및 Phase 2 seed가 적용된 로컬/시연 DB에서 아래 순서로 적용한다.

```sh
.venv/bin/python scripts/import_phase2_policy.py --check

# 새 시연 DB라면 먼저 기존 기반 데이터를 넣는다.
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/seed.sql

# 기존 시연 DB에는 이 단계로 수신 문서 revision을 추가한다.
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/policies/apply.sql
```

SQL은 A/B 회사 정책 revision 2와 연결 가격·승인 경로·회수 규칙 revision 2를 하나의 트랜잭션에 추가한다. 정책만 갱신하면 서버의 버전 일치 검사에 걸리므로 연결 버전도 함께 추가한다. 가격 금액·승인 순서·회수 조건은 기존 값을 복사한다. 기존 revision 1·승인 계획·회수 스냅샷은 보존한다.

같은 파일의 재적용은 중복을 만들지 않는다. 다른 내용의 revision 2, 이후 revision, 다른 회사/정책 family, 예상과 다른 기반 데이터가 있으면 중단한다. 적용 중 하나라도 실패하면 전체를 롤백하며 기존 이력을 UPDATE/DELETE하지 않는다.

새 요청과 새 점검부터 revision 2를 사용한다. 적용 전에 생성한 승인 계획은 최신 정책과 달라져 실행 시 수동 검토가 필요할 수 있다. 기존 회수 스냅샷은 당시 revision 1을 유지한다. 이미 사용한 revision 2의 원문을 바꾸려면 새 revision 배포가 필요하다.

**이번 환경에서는 Docker 소켓 접근과 임시 PostgreSQL의 공유 메모리 생성이 제한되어 실제 DB 적용·통합 검사는 실행하지 못했다.** 실행 중 DB에 반영됐다고 간주하지 않는다. 위 SQL을 적용해야 Phase 2 서비스가 새 자료를 사용한다.

## 확인된 차이와 반영 범위

| 항목 | 수신 문서 | 현재 처리 |
|---|---|---|
| Figma 가격 | Professional Full 월 16달러 예시 | mock 계약 월 15.00 USD 유지. 정가와 계약가를 혼동하지 않도록 적용 범위에 명시 |
| Tableau 직무 | 분석 직무 | 서버 DEV/ANALYST 허용 유지. 직무 기준 정합화 필요 |
| Databricks | 작업 실행 주체의 데이터 접근 확인 필요 | 현재 사실 모델은 요청자 중심. 실행 주체 사실·검증은 후속 구현 필요 |
| Notion 기밀 편집 | 추가 부서장 승인, 문서상 확장 범위 | 해당 조건별 추가 승인 규칙은 후속 구현 필요 |
| Figma View | 무료 보기·댓글 좌석 | mock 권한 목록에는 편집 좌석만 있음. Viewer 요청은 다른 권한으로 대체하지 않고 수동 검토 |
| Admin→Read | 읽기로 충분한 요청 사유인 경우에만 제안 | 기존 최소 권한 제안 유지. 요청 목적 충족 여부의 정밀 검증은 후속 과제 |
| 회수 | 후보 선별·알림, 사람이 결정 | 실제 회수·예산 환입은 수행하지 않음. 미확인 값 처리와 활성 TF 기준은 회사별 적용 설명에 명시 |

이번 작업은 RAG 검색·인용과 정책 revision 연결의 반영이다. 문서 문장을 실행 코드로 해석하거나 실제 SaaS 권한·계약 가격을 자동 변경하지 않는다. 기존 smoke/full 평가는 revision 1 baseline을 유지하며, 수신 정책의 DB 적용은 `Phase2FoundationIT`의 추가 검사로 확인한다.

## 재생성과 검사

```sh
.venv/bin/python scripts/import_phase2_policy.py
.venv/bin/python -m pytest agent/tests/test_phase2_policy_import.py -q
```

원문과 생성 파일은 함께 커밋한다. 기존 `generate_phase2_seed.py`는 revision 1 baseline 전용이며 이 수신 문서를 덮어쓰지 않는다.

## 최종 시나리오 v4 적용 (앞선 revision 2 설명 이후)

현재 시나리오는 `scenarios-v4.json`과 **정책/가격/승인 경로/회수 규칙 revision 3**을 사용한다. revision 1·2는 비교 기준과 기존 이력을 위해 보존했다. `scripts/align_phase2_v4.py`가 회사별 `company-*-policy-v3.md`와 `apply-v4.sql`을 생성한다.

- Figma Professional Full 16.00 USD, 잔여 100.00 → 84.00. Copilot 19, Notion Business 20, Tableau Enterprise Explorer 70은 제공 문서의 정가 기록(PUBLIC_LIST_PRICE)이다. 이번 작업에서 공식 웹 원문을 재검증하지 않았다.
- Snowflake 120·Databricks 80은 시연 사용량 가정, Salesforce·Datadog 0은 시연 계약 가정으로 SYNTHETIC_CONTRACT를 유지한다.
- 적용 SQL은 SYNTHETIC 출처의 KNOWN 사용 이력만 시연 적용 시각으로 갱신한다. UNKNOWN 관측이나 실제 제공자 데이터는 갱신하지 않는다. 다음 날짜에 수동 시연할 때는 모의 관측 시각을 다시 준비해야 한다.
- Databricks 모의 데이터에는 Run as 실행 주체·데이터 접근 사실을 명시한다. 실제 회사 사실은 추측해 채우지 않는다. 해당 사실이 없으면 수동 검토한다. Tableau 신청 직무는 ANALYST다.
- 기존 SQL 또는 원문 revision을 덮어쓰지 않는다. revision 3 적용 SQL은 동일 내용으로 재실행할 수 있고, 다른 내용이나 더 높은 revision이 있으면 중단한다.

백엔드 재시작으로 **V8 migration을 먼저 적용**한 뒤, 새 시연 DB는 `seed.sql → policies/apply.sql → policies/apply-v4.sql` 순서로 적용한다. revision 2까지 이미 적용했다면 아래 명령만 실행한다. revision 3 적용 후에는 이전 apply.sql을 다시 실행하지 않는다.

```sh
.venv/bin/python scripts/align_phase2_v4.py --check
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/policies/apply-v4.sql
```

### 시연 DB 적용 절차와 확인

| 단계 | 적용 주체 | 재실행 |
|---|---|---|
| V1~V8 | backend 기동 시 Flyway 자동 | Flyway가 이력으로 건너뜀 |
| `seed.sql` | backend 기동 시 `DemoSeed` 자동 (`DEMO_ENABLED=true`, `DEMO_PHASE2_SEED_PATH`). postgres 컨테이너 init 스크립트가 아님 | `ON CONFLICT DO NOTHING`, 기동마다 다시 실행돼도 기존 행 보존 |
| `apply.sql` (revision 2) | 수동 `psql` | revision 2만 있으면 중복 없이 통과. **revision 3 적용 후에는 "later revision" 예외로 롤백**(데이터 변화 없음) |
| `apply-v4.sql` (revision 3) | 수동 `psql` | 동일 내용 재실행 안전. 단 SYNTHETIC·KNOWN `assignment_usage.observed_at`을 실행 시각으로 다시 갱신 |

compose 시연 DB를 시나리오 값(Figma 16.00 USD, B사 예산 100.00 → 84.00)으로 맞추는 순서:

```sh
docker compose up -d --build          # V8 + seed.sql 자동 적용, backend healthy까지 대기
psql_demo() { docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'; }
# 아래 확인 쿼리의 revision이 1이면 apply.sql부터, 2이면 apply-v4.sql만, 3이면 생략
psql_demo < data/phase2/policies/apply.sql
psql_demo < data/phase2/policies/apply-v4.sql
```

확인 쿼리(`psql_demo <<'SQL' ... SQL`로 실행):

```sql
-- 회사별 현재 정책 revision: P2_A·P2_B 모두 3
SELECT c.code, max(p.revision) AS policy_revision
FROM policy_revisions p JOIN companies c ON c.id = p.company_id
WHERE c.code IN ('P2_A','P2_B') GROUP BY c.code ORDER BY c.code;

-- revision 3의 Figma 가격: 16.00 USD / PUBLIC_LIST_PRICE / policy_revision 3 (revision 1·2의 15.00은 보존)
SELECT c.code, pr.revision, pr.monthly_amount, pr.currency, pr.source_kind, pr.policy_revision
FROM pricing_revisions pr
JOIN companies c ON c.id = pr.company_id
JOIN entitlements e ON e.id = pr.entitlement_id
JOIN resources r ON r.id = e.resource_id
WHERE r.platform = 'FIGMA' ORDER BY c.code, pr.revision;

-- P-06(B사 Figma) 계산 기준 예산: 100.00. 84.00은 저장값이 아니라 새 요청 계획에서 100.00 - 16.00으로 계산
SELECT d.code, b.remaining_monthly_amount, b.currency
FROM department_budgets b JOIN departments d ON d.id = b.department_id
WHERE d.code = 'P2_B_DEV';
```

예산이 100.00이 아니면 이전 시연 요청이 예산을 사용한 상태다. 이 절차는 예산을 되돌리지 않는다.

평가 실행기는 격리 회사에 세 SQL을 순서대로 적용하고 v4 자연어 입력·근거 조항을 사용한다. DB의 과거 계획은 수정하지 않으며 새 요청·재분석·새 점검부터 revision 3을 사용한다.

정기 점검은 `PHASE2_RECLAIM_SCHEDULE_ENABLED=true`와 대상 `reclaim_scopes.enabled=true`가 모두 필요하다. 시각은 `PHASE2_RECLAIM_CRON`으로 설정하며 기본은 `0 0 9 * * *`(Asia/Seoul)다. 기본 배포는 수동 시연 모드이고 자동 점검은 명시적으로 활성화한다.
