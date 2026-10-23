# RAG 정책 자료와 비용 해석

현재 실행 기준은 회사 정책 묶음 **revision 4**와 `data/phase2/scenarios-current.json`이다. 수신 원문과 정책 revision 1~3은 비교・감사 이력으로 보존한다. 원문 문서의 버전과 DB 정책 묶음 revision은 별도 식별자다.

## 자료별 역할

| 파일 | 역할 |
|---|---|
| policy_corpus.md | 수신 POL-01~14・공식 요약 14개 원문. 총 28문서・107청크 |
| company-*-policy-v2.md / apply.sql | 원문을 회사별 정책에 연결한 revision 2 |
| company-*-policy-v3.md / apply-v4.sql | 기존 시나리오 v4 정합화 revision 3. Figma 16달러・제품 전제・회수 기준 |
| company-*-policy-v4.md / apply-costs.sql | 권한 추가・좌석 확보・사용량 예산을 구분한 revision 4. 이전 가격을 참고 단가로 보존하고 비용 규칙・조직 범위 라이선스 관측 추가 |
| ../../../agent/unlockops/access/approval-review-guide.md | 서버 사실과 근거를 설명하는 보고서 지침 |

POL은 사내 자격・절차, OFF는 제품 기능・라이선스 개념, FLOW는 승인 순서를 설명한다. 개인의 실제 보유 상태・가격・예산・담당자 ID는 서버 사실을 사용한다. 제공 가격・확인일은 자료의 기록이며 현재 계약가를 뜻하지 않는다.

## 검색과 보고서

- 규정은 조항별, 제품 요약은 핵심 요약・진단 힌트・원문별로 나눈다. article은 문서 ID・플랫폼・원문 버전을 보존한다.
- MCP는 요청 ID로 회사・정책 revision・해시를 확인한다. 승인은 대상 플랫폼과 COMMON, 회수는 고정 스냅샷의 정책만 사용한다.
- 로컬 문자 n-gram TF-IDF・코사인 검색과 정확 조회를 사용한다. 임베딩 모델이나 벡터 DB는 필요하지 않다.
- 승인 근거에서는 회수 조항을 제외하고 GitHub 좌석/저장소, TF/일반 범위를 구분한다.
- 회사 정책 revision 4 BASELINE은 참고 단가와 이번 요청의 비용을 구분한다. 보고서는 `review_facts.cost_assessment`와 승인 계획을 사용하고 정가 예시로 0원 계획을 덮어쓰지 않는다.
- 단일 승인 실행기는 제거했다. 기존 data/policy_corpus.md 등 원본 자료와 과거 기록은 보존한다.

## 현재 비용 기준

| 요청 | 서버 확인과 비용 |
|---|---|
| Notion E-02 페이지 편집 | 대상 워크스페이스 Business 라이선스 보유 확인. 참고 단가 20 USD, 추가 비용・예산 반영 0 |
| Tableau P-05 프로젝트 편집・게시 | 대상 사이트 Explorer 및 데이터 접근 확인. 참고 단가 70 USD, 추가 비용・예산 반영 0 |
| GitHub Copilot / Figma Full 좌석 | 대상 조직에서 이미 보유하면 0. 미보유와 신규 구매 필요 확인 시 시연 단가 19 / 16 USD 적용 |
| Snowflake / Databricks | 120 / 80 USD는 시연의 내부 사용량 예산 배정이며 권한 구매 비용・실제 청구액이 아님 |
| Salesforce 담당 고객 권한 / Datadog 조회 | 기존 이용 범위의 권한 변경. 서버 비용 규칙과 관측에 따름 |

라이선스는 회사・사용자・플랫폼・조직 범위・라이선스 코드로 확인한다. 계정이 있다는 사실만으로 기존 멤버・Full・Explorer 보유를 추측하지 않는다. 관측 누락・미확인・만료는 0원으로 처리하지 않는다. 미배정 선구매 좌석・업그레이드 차액・일할 청구는 자동 계산하지 않으며 신규 구매 필요가 불명확하면 수동 검토한다.

기존 라이선스 권한 요청에 신규 멤버 등록이나 좌석 구매를 자동 포함하지 않는다. 0원도 사내 정책・업무 범위・사람의 순차 승인을 유지한다. 세부 기준은 [승인 판단 조건](../../../docs/approval-decision-conditions.md)을 따른다.

## DB 적용

V10 migration이 비용 규칙과 조직 범위 라이선스 관측 테이블을 추가한다. Compose 시연의 DemoSeed는 baseline → 누락된 revision 2 → 3 → 4를 한 트랜잭션으로 준비한다. 이미 설치된 revision은 건너뛰고 기존 예산・요청・라이선스 관측은 초기화하지 않는다.

새 backend를 빌드・기동하면 Flyway와 DemoSeed가 적용한다.

```sh
docker compose up -d --build
```

시연 모드・DEMO_SEED_PATH가 설정된 경우에만 자동 준비한다. 개별 수동 준비는 V10 이후 `seed.sql → policies/apply.sql → policies/apply-v4.sql → policies/apply-costs.sql` 순서다. **기존 revision 3 DB에는 apply-costs.sql만** 적용한다.

```sh
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/phase2/policies/apply-costs.sql
```

revision 4 적용 후 apply.sql・apply-v4.sql을 다시 실행하지 않는다. 과거 import는 더 높은 revision이 있으면 중단한다. apply-costs.sql의 동일 내용 재적용은 안전하며 변경된 동일 revision이나 충돌한 비용 규칙이면 중단한다. 규칙・가격・정책・승인 경로・회수 규칙을 원자적으로 연결한다. 새 요청・재분석・새 점검부터 최신 revision을 사용하며 기존 승인 계획과 다르면 재검토가 필요하다.

확인 쿼리:

```sql
SELECT c.code,max(p.revision) AS policy_revision
FROM policy_revisions p JOIN companies c ON c.id=p.company_id
WHERE c.code IN ('P2_A','P2_B') GROUP BY c.code ORDER BY c.code;
-- A/B 모두 4

SELECT c.code,r.platform,e.code,cr.operation,cr.billing_scope,cr.required_license
FROM access_cost_rules cr JOIN companies c ON c.id=cr.company_id
JOIN entitlements e ON e.id=cr.entitlement_id JOIN resources r ON r.id=e.resource_id
WHERE cr.policy_revision=4 ORDER BY c.code,r.platform;

SELECT platform,billing_scope,license_code,coverage,purchase_required,observed_at
FROM saas_license_facts ORDER BY company_id,user_id,platform;
```

참고 단가가 20・70으로 조회되는 것은 정상이다. 이번 예산 반영액은 서버 assessment와 plan에서 0으로 확인한다. 실제 공급자 결제 API는 호출하지 않는다.

## 재생성과 검사

```sh
PYTHONPATH=agent:rag .venv/bin/python scripts/import_phase2_policy.py --check
PYTHONPATH=agent:rag .venv/bin/python scripts/align_phase2_v4.py --check
PYTHONPATH=agent:rag .venv/bin/python scripts/align_access_costs.py --check
PYTHONPATH=agent:rag:mcp .venv/bin/python -m pytest agent/tests/test_policy_import.py agent/tests/test_approval_review.py -q
python3 scripts/evaluate_phase2.py --plan --suite full
```

--check는 생성물 일치만 검사하며 DB에 접속하지 않는다. full 33건・smoke 9건의 실제 통합 평가는 --run으로 격리 DB에 적용한다. 정책이나 비용 가정을 바꿀 때는 배포된 revision을 고치지 않고 새 revision과 평가를 함께 준비한다.
