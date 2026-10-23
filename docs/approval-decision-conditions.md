# 승인 판단 자료·비용 규칙·상태

요청 → 사전 조건 → 현재 사실 → 추가 비용 판단 → 정책・예산 판정 → 사람의 순차 승인 → 실행・검증으로 연결한다.
공통 상태・사유는 [reason-status.json](../contracts/phase2/reason-status.json), 현재 시나리오는 [scenarios-current.json](../data/phase2/scenarios-current.json)을 따른다. 변경 전 [scenarios-v4.json](../data/phase2/scenarios-v4.json)과 정책 revision 1~3은 비교 이력이다.

## 세 가지 비용 작업

| 작업 | 서버 기준 | 예산 처리 |
|---|---|---|
| PERMISSION_ONLY | 기존 라이선스 범위에서 권한만 추가. 필요한 라이선스가 지정됐다면 대상 조직에서 COVERED 확인 | 추가 비용 0. 정책・사람 승인은 유지 |
| PURCHASE_SEAT | 명시적인 좌석 요청. 동일 상품 보유 시 재사용, 미보유와 신규 구매 필요가 확인되면 단가 적용 | 이번 추가 비용만 비교・차감 |
| USAGE_ALLOCATION | Snowflake・Databricks 시연의 내부 사용량 예산 배정 | 예상 사용 예산을 비교・배정. 실제 공급자 청구액으로 표현하지 않음 |

월 참고 단가(`unit_monthly_amount`), 이번 예상 추가 비용(`incremental_monthly_amount`), 내부 예산 반영액(`budget_monthly_amount`)을 구분한다. 사용량 배정의 실제 추가 청구는 미확인이므로 incremental_monthly_amount는 null이다. 기존 plan.monthly_amount는 내부 예산 반영액이고 plan.cost_basis는 그 근거다.

기본 `account_exists`나 `license_active`만으로 특정 워크스페이스・제품의 이용 자격을 추정하지 않는다. `access_cost_rules`는 정책・권한 revision에 연결한 비용 작업, 조직 범위, 필요한 라이선스를 선언한다. `saas_license_facts`는 회사・사용자・플랫폼・조직 범위・라이선스 코드별 보유 상태와 관측 근거를 저장한다.

신규 구매는 NOT_COVERED만으로 확정하지 않는다. purchase_required=true까지 확인해야 한다. 미배정 선구매 좌석이 있거나 업그레이드・일할 청구 조건이면 자동 계산하지 않고 별도 근거가 필요하다. 비용 규칙이 없을 때는 명시적인 0원 권한만 유지하며, 유료 좌석 호환은 V9에서 이관한 기존 조직의 정책 revision 1・부서 예산 단가 출처에만 적용한다. 새 정책의 규칙 누락과 구매 규칙의 조직 범위・라이선스 코드 누락은 수동 검토한다.

## 현재 SaaS와 기대 결과

| 시나리오 | 요구 사실 | 참고 단가 / 예산 반영 | 기대 분석 결과 |
|---|---|---|---|
| E-02 Notion 편집 | 대상 워크스페이스 Business 보유, TF 소속・기본 계정・업무 배정 확인, 편집 권한 미보유, 잔여 10 USD | 20 / 0 USD | WAITING_APPROVAL / ELIGIBLE |
| P-05 Tableau 프로젝트 게시 | 대상 사이트 Explorer 보유, 기존 데이터 접근・업무 배정 확인 | 70 / 0 USD | WAITING_APPROVAL / ELIGIBLE |
| BUDGET-INSUFFICIENT | Copilot 미보유・신규 구매 필요, 잔여 10 USD | 19 / 19 USD | ON_HOLD / BUDGET_INSUFFICIENT |
| BUDGET-EQUAL | Copilot 신규 구매, 잔여 19 USD | 19 / 19 USD | WAITING_APPROVAL / ELIGIBLE |
| BUDGET-ABOVE | Copilot 신규 구매, 잔여 30 USD | 19 / 19 USD | WAITING_APPROVAL / ELIGIBLE |
| BUDGET-FREE | 동일 조직의 Copilot 보유 확인, 잔여 10 USD, 현재 자원 할당은 아직 없음 | 19 / 0 USD | WAITING_APPROVAL / ELIGIBLE |

Figma Full도 동일한 좌석 기준을 적용한다. 현재 시연 신청자는 Full 미보유・신규 구매 필요 관측을 사용하므로 예산 반영액은 16 USD다. Notion 신규 유료 멤버 등록이나 Tableau 라이선스 업그레이드를 페이지・프로젝트 권한 요청에 자동 포함하지 않는다.

| 정보 부족・불일치 | 처리 |
|---|---|
| 라이선스 관측 누락・UNKNOWN・만료・미래 시각, 신규 구매 필요 불명확 | MANUAL_REVIEW / BUDGET_UNAVAILABLE |
| 권한만 요청했는데 필요한 라이선스 미보유 확인 | MANUAL_REVIEW / OUT_OF_SCOPE, 라이선스 선확보 안내 |
| 비용・통화 확인 후 예산 부족 | ON_HOLD / BUDGET_INSUFFICIENT |
| 승인 후 가격・라이선스 변화로 승인 금액/비용 기준 변경 | MANUAL_REVIEW / PLAN_REVIEW_REQUIRED |

0원도 승인 절차를 건너뛰지 않는다. 승인/실행 때 서버가 최신 계획을 재검사하고, 모의 실행은 예산・라이선스 관측을 잠근 뒤 부여・예산・영수증・좌석 확보 관측을 함께 저장한다. 같은 실행 키 재전달은 기존 영수증을 반환한다. 현재 차감은 내부 부서 예산이며 SaaS 결제 API를 호출하지 않는다.

## RAG와 서버 책임

RAG는 제품의 권한・라이선스 개념과 사내 규정을 설명한다. 실제 직원의 라이선스・추가 비용은 서버 관측과 비용 규칙으로 판단한다. 가격 문서의 정가를 0원 계획에 다시 적용하지 않는다. 보고서는 참고 단가와 예산 반영액을 나누고 확인 근거・관측 시각을 설명한다. 수신 원문은 보존하고 비용 해석 보완은 회사 정책 revision 4 BASELINE과 보고서 지침에 반영한다.

## 평가 사전 검증

full은 33건, smoke는 9건이다. E-02・P-05와 비용 경계 4건은 `preconditions`・`decision_rule`・기대 상태를 선언한다. 격리 fixture 설치 후 실제 DB의 회사・사용자・자원・권한・가격 버전・정책 버전・비용 작업・조직 범위 라이선스・잔여 예산을 요청 접수 전에 대조한다. 구매 필요 여부도 대조하고 라이선스의 관측 시각・만료 시각・관측 출처가 유효한지 DB 시각으로 확인한다. 모든 정책 검증을 대체하지 않으며 업무 판정은 서버가 다시 수행한다.

준비 조건이 다르면 해당 건은 평가 전용 PRECONDITION_FAILED, 나머지는 NOT_RUN으로 남기고 전체 BLOCKED로 요청을 중단한다. report.json의 precondition_check.expected / observed / mismatches에 차이를 기록한다. 업무 API의 상태값을 추가하는 것은 아니다. 준비 조건을 통과한 뒤 실제 결과가 다르면 FAIL로 구분한다.

가격/정책 revision 4와 V10이 적용돼야 새 동작을 사용한다. Compose 시연은 새 backend 기동 때 누락분을 준비하며 기존 예산・승인 이력을 초기화하지 않는다. 기존 승인 계획은 최신 조건과 다르면 재검토가 필요하다. 상세 적용은 [정책 자료 안내](../data/phase2/policies/README.md)를 따른다.
