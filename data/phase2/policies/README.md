# Phase 2 RAG 정책 자료

현재 통합 서버는 Compose 시연 초기화 시 baseline → 누락된 revision 2 → revision 3을 한 트랜잭션으로 준비한다. 이미 설치된 revision은 다시 쓰지 않는다. 이 경로는 DEMO_ENABLED와 DEMO_SEED_PATH를 명시한 시연에만 적용하며 아래 수동 적용 절차도 유지한다. 구 v1 정책 도구·별도 실행기는 제거했고 수신 규정·공식 요약의 안내 기능은 현재 승인 그래프에 통합했다.

현재 시나리오는 **v4**, 연결하는 정책·가격·승인 경로·회수 규칙은 **revision 3**이다.
revision 1·2는 과거 이력과 비교 기준으로 보존한다. 파일을 편집하거나 서버를 재시작하는 것만으로 실행 중 DB의 정책이 교체되지는 않는다.

## 자료별 역할

| 파일 | 역할 |
|---|---|
| `policy_corpus.md` | 수신 원문: 사내 규정 POL-01~14와 공식 제품 요약 14개, 총 28개 문서·107개 청크 |
| `company-*-policy-v2.md` / `apply.sql` | 최초 원문 연결 revision 2. 당시 가격·승인 경로·회수 규칙을 보존 |
| `company-*-policy-v3.md` / `apply-v4.sql` | v4 정합화 revision 3. Figma 16달러, 가격 출처·SaaS 전제조건·회수 기준 연결 |
| `../../../agent/unlockops/access/approval-review-guide.md` | 승인 보고서 작성 지침. 회사 정책이나 실행 권한을 추가하는 문서는 아님 |

공식 링크·확인일·가격은 제공 자료의 기록이다. 외부 원문에서 현재 가격을 재검증한 값으로 표시하지 않는다.
공식 요약은 제품의 기능을 설명하고, POL은 회사의 자격·절차를 설명한다. 특정 직원의 소속·계정·예산은 서버에서 조회한다.
문서 전체의 역할·지원 차이·이번 에이전트 보완은 [승인 RAG 점검](../../../docs/rag-approval-review.md)에 정리했다.

## 검색과 승인 보고서

- `rag/unlockops_rag/corpus.py`는 규정을 조항별로, 공식 요약을 요약·진단 힌트·원문별로 나눈다.
- article은 `POL-14 | FIGMA | v1.0 | 제3조(좌석 비용)`처럼 원문 ID·플랫폼·버전을 보존한다. DB 회사 묶음 revision·문서 ID·해시는 별도 필드다.
- MCP는 작업 ID로 회사 정책을 조회한다. 승인은 해당 플랫폼과 COMMON만, 회수는 점검 스냅샷에 고정된 정책을 사용한다.
- 검색은 로컬 문자 n-gram TF-IDF·코사인 유사도다. Phase 2에는 임베딩 모델이나 벡터 DB가 필요하지 않다.
- 승인 에이전트는 검색과 정확 조회 결과를 검증한 후 회수 조항을 제외한다. GitHub 좌석과 저장소의 공식 자료를 구분하고, TF가 필요하지 않은 자원에서는 TF 규정을 제외한다.
- 보고서의 금액·통화·대상·TF 사실은 서버 `review_facts`와 승인 계획을 사용한다. 공식 가격 예시로 빈 예산을 채우지 않는다. 보고서 작성·검토에는 별도의 작성 지침을 적용한다.
- v1 단일 승인 경로는 `data/policy_corpus.md`와 `data/company-a-access-matrix.md`를 계속 사용한다. v1 파일을 v2 자료로 덮어쓰지 않는다.

## DB 적용

생성기는 SQL만 만들며 DB에 자동 접속하지 않는다. V8 이상 migration을 먼저 적용한다.
새 시연 DB의 순서는 `seed.sql → policies/apply.sql → policies/apply-v4.sql`이다.

```sh
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/seed.sql
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/policies/apply.sql
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/policies/apply-v4.sql
```

revision 2까지 적용했다면 마지막 명령만 실행한다. revision 3 적용 후 이전 `apply.sql`을 다시 실행하지 않는다.
각 SQL은 동일 내용 재적용에는 멱등하며, 동일 revision의 다른 본문·다른 정책 family·더 높은 revision이 있으면 중단한다.
정책·가격·승인 경로·회수 규칙의 연결은 한 트랜잭션으로 적용한다. 기존 immutable revision과 과거 승인 계획·회수 스냅샷은 변경하지 않는다.
새 요청·재분석·새 점검부터 최신 revision을 사용한다. 기존 승인 계획과 최신 조건이 다르면 재검토가 필요할 수 있다.

## v4 해석과 지원 범위

- Figma Professional Full 16.00 USD와 예산 100.00 → 84.00은 제공 자료 기반 시연이다. Copilot 19, Notion Business 20, Tableau Enterprise Explorer 70도 PUBLIC_LIST_PRICE로 구분한다.
- Snowflake 120·Databricks 80은 사용량 가정이다. Salesforce·Datadog 0은 시연 계약 가정이다. SYNTHETIC_CONTRACT를 실제 계약으로 표시하지 않는다.
- Databricks는 요청자와 Run as 실행 주체의 데이터 접근을 따로 확인한다. Tableau의 시연 허용 직무는 ANALYST다.
- Figma 무료 View 카탈로그, Notion 기밀 편집의 추가 승인, Slack 외부 게스트는 현재 승인 범위의 확장이 필요하다. RAG 문장만으로 지원된다고 간주하지 않는다.
- 개별 회수 정보 부족은 추가 확인 목록에 남기고 정상 점검을 마칠 수 있다. 전체 조회 실패는 FAILED/SCAN_FAILED다. 점검 완료는 실제 회수·절감·예산 환입이 아니다.
- 합성 데이터의 KNOWN 사용 관측만 v4 SQL 적용 시각으로 갱신한다. UNKNOWN이나 실제 제공자 관측을 추측해 갱신하지 않는다.
- 자동 점검은 `PHASE2_RECLAIM_SCHEDULE_ENABLED`와 대상 scope의 enabled를 모두 켜야 한다. 기본 cron은 `0 0 9 * * *`, Asia/Seoul이다.

## 재생성·검사

```sh
.venv/bin/python scripts/import_phase2_policy.py --check
.venv/bin/python scripts/align_phase2_v4.py --check
.venv/bin/python -m pytest agent/tests/test_policy_import.py agent/tests/test_approval_review.py agent/tests/test_workflows.py -q
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
현재 생성 결과를 검사하려면 `--check`를 쓴다. 의도적으로 다시 생성할 때만 이를 생략한다.
배포한 revision을 변경하려면 새 revision 생성기·연결 SQL·서버 규칙·평가를 함께 준비해야 한다.
보고서 지침과 이번 근거 선택·서버 조회 필드 보완에는 새 정책 revision이나 DB migration이 필요하지 않다.
