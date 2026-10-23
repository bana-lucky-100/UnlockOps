# UnlockOps 통합 전 점검 기록

이 문서는 통합 전 정리 대상 기록이다. 현재 실행 구조는 [업무 실행 구조](architecture.md), 실제 변경·검증은 [구현 기록](../IMPLEMENTATION.md)을 따른다.

현재 시나리오 v4를 처리하는 실행 경로 하나를 기준으로 삼고, 기존 단일 승인 경로는 필요한 기능을 옮긴 뒤 종료한다. 승인과 회수라는 업무 구분은 유지한다. `phase2`라는 개발 단계 때문에 남은 중복 실행 경로와 호환 분기를 정리하는 작업이다.

점검 기준은 2026-10-23 현재 작업 트리다. 커밋 전 승인 RAG 보고서 보강도 포함한다. 이 문서는 팀별 작업 분담과 제거 후보를 정리하며, 업무 코드·DB·큐를 변경하지 않는다. 기존 경로는 아직 연결돼 있으므로 아래의 제거 후보는 현재의 미사용 파일 목록과 다르다.

**전체 담당 영역과 결과물**

| 영역 | 현재 남은 분리 | 담당자가 만들 결과물 | 우선순위 |
|---|---|---|---|
| 프론트 | 계정별 구/신 화면, 화면 모델·상태·접수 로직 | 최신 계약을 쓰는 한 가지 화면 체계 | 높음 |
| 백엔드 | 단일 승인과 다단계 승인의 서비스·API·내부 API | 다단계 승인 기준의 한 가지 업무 처리 경로 | 높음 |
| 승인 에이전트 | 기존 interrupt 그래프와 새 분석·실행 그래프 | 필요한 기존 기능을 반영한 분석·실행 경로 | 높음 |
| 회수 에이전트 | 그래프 중복은 없음. 공통 모듈이 phase2에 종속 | 회수 그래프 유지, 공통 모듈 전환 | 중간 |
| Worker와 MCP | 구 큐 소비·결과 처리, 구/신 도구 동시 등록 | 현재 업무만 실행하는 Worker와 도구 목록 | 높음 |
| 공통 계약 | v1 업무 모델과 v2 생성 계약, 혼합 도구 registry | 업무 계약과 도구 계약의 단일 기준 | 가장 먼저 |
| 정책과 데이터 | 구 파일 정책, 회사별 정책 revision, 여러 seed 단계 | 현재 정책 조회·시연 준비 진입점 통일 | 높음 |
| 테스트와 문서 | 구 경로 전용 테스트와 신규 평가, 문서 기준 분산 | 현재 흐름의 회귀 검사와 팀 공통 명세 | 각 영역과 함께 |

**1. 프론트**

경로 기준은 `frontend/src/`다.

| 정리 대상 | 기존 경로 또는 구현 | 현재 시나리오 경로 | 권장 작업 |
|---|---|---|---|
| 업무 화면 | `views/RequesterHome.vue`, `ApproverHome.vue`, `MyRequests.vue`, `RequestDetail.vue` | `views/phase2/AccessList.vue`, `AccessNew.vue`, `AccessDetail.vue` | 새 계약으로 화면을 통일. 기존 화면의 필요한 디자인·검색·표시 기능을 옮긴 뒤 구 화면 종료 |
| 계정별 라우팅 | `router.ts`, `session.ts`의 `workflow_version` 분기 | `/access`, `/access/new`, `/access/:id`, `/reclaim/...` | 버전별 화면 분기를 제거. 로그인·역할·조회 권한에 따른 분기는 유지 |
| 타입과 API 함수 | `api.ts`의 구 `Problem`·`Status`·4개 플랫폼 타입 | `contracts/phase2.ts`, `phase2/api.ts` | 업무 타입·호출 함수를 최신 계약으로 통합. `api.ts`의 HTTP·CSRF·오류 처리와 인증용 타입은 계속 필요 |
| 표시 로직 | `components/StatusBadge.vue`, `StageBar.vue`, `lib/status.ts`, `lib/requestView.ts`, `lib/platforms.ts` | `components/phase2/WorkflowBadge.vue`, `phase2/presentation.ts` | 상태·승인 단계·10개 플랫폼 표시를 공통화. 구 4개 플랫폼 목록을 기준으로 덮어쓰지 않음 |
| 요청 중복 방지 | `problemSubmission.ts`, `composables/useProblemSubmission.ts` | `phase2/submission.ts` | 접수 기능 하나로 통합. 같은 입력 재시도의 키 재사용·중복 클릭 차단·사용자 전환 처리를 유지 |
| 화면과 스타일 이름 | 기존 화면 CSS와 `phase2/style.css`, `components/phase2/Workspace.vue` | 새 화면이 기존 `AppShell.vue`를 이미 재사용 | 공통 디자인을 추출하고 단계명 경로를 업무명으로 변경. `AppShell.vue`, 로그인, 세션, `lib/polling.ts`, 디자인 토큰은 삭제 대상 아님 |

완료 기준: 최신 계약을 쓰는 화면만 열리고, 같은 사용자에게 구/신 화면 체계가 갈라지지 않는다. 승인 순서·보류·안내 완료·회수 추가 확인을 표시한다. 디자인 변경과 업무 계약 변경을 구분해 검토한다.

**2. 백엔드**

경로 기준은 `backend/src/main/java/com/unlockops/`다.

| 정리 대상 | 기존 구현 | 현재 시나리오 구현 | 권장 작업 |
|---|---|---|---|
| 접수와 공개 API | `problem/controller/ProblemController`, `problem/service/ProblemService`, `approval/controller/ApprovalsController` | `phase2/access/AccessV2Controller`, `AccessWorkflowService` | 현 다단계 승인 API로 클라이언트를 통일한 뒤 구 접수·결정 API 종료. 기존 통계가 필요하면 현 데이터 기준으로 옮김 |
| 승인 상태 전환 | `approval/service/ApprovalDecisionService`, `ApprovalCompletionPolicy`, `ApprovedExecutionService` | `phase2/access/AccessWorkflowService` | 승인 기록·다음 단계·전체 승인 완료·실행 전환의 책임을 정리. 단일 승인 구현을 별도로 유지하지 않음 |
| 계획과 권한 실행 | `grant/service/GrantPolicy`, `GrantExecutionService` 등 | `phase2/access/AccessPlanningService`, `AccessExecutionService` | 현재 권한 항목·revision·계획 해시 기준으로 통일. 구 역할 규칙을 새 흐름에 무조건 합치지 않음 |
| 에이전트용 내부 API | `/internal/access-context`, `/internal/access-verifications`, `/internal/resources/resolve`, `/internal/problems/{id}/grant` | `/internal/v2/problems/{id}/context`, `assessment`, `execute`, `verify` | MCP 전환 후 구 내부 API와 해당 호출자 전용 service/repository 제거 후보를 확정 |
| 버전별 조회와 계정 | `ProblemRepository`의 `contract_version=1` 필터, `UserRepository.profile()`의 LEGACY→workflow_version 변환 | `Phase2Store.problem()`의 `contract_version=2` 필터, 새 회사·담당 범위 검사 | 신규 업무는 한 경로로 통일. 기존 기록은 읽기 처리와 신규 실행을 구분. 회사 격리·담당 범위 권한 검사는 유지 |
| 패키지 이름 | 기존 `access`, `approval`, `grant`, `problem`과 신규 `phase2/access`, `phase2/reclaim`, `phase2/common` | 일부 업무가 개발 단계 아래 묶임 | 최종적으로 access/reclaim/common/messaging 등 업무·공통 책임에 배치. 같은 이름 충돌과 의존성을 해결한 뒤 이동 |

`auth`, `config`, 공통 오류·JSON, Outbox 발행기, Inbox 중복 방지는 새 코드도 사용하는 기반이다. 구 경로가 들어 있는 상위 패키지를 통째로 삭제하지 않는다. 특히 `Phase2Results`도 `messaging/service/InvalidAgentMessageException`을 사용한다.

기존 준비 문서는 `ApprovalCompletionPolicy`를 다단계 승인용으로 확장하도록 했지만, 실제 구현은 별도 `AccessWorkflowService`를 사용한다. 이번 통합에서 기존 클래스 사용 자체를 목표로 삼을 필요는 없다. 현재 정확한 처리 규칙과 책임을 보존하며 중복 구현을 없애는 것이 목표다.

완료 기준: 접수·승인·반려·보류·재개·실행·검증이 현 서비스 경로로만 진행된다. 본인 승인 금지, 순차 승인, 계획 버전 검증, 최신 조건 재검사, 예산·부여·영수증의 원자 저장을 유지한다.

**3. 승인 에이전트**

경로 기준은 `agent/unlockops/`다.

| 정리 대상 | 현재 연결 | 권장 작업 |
|---|---|---|
| 구 승인 그래프 | `access/graph.py`를 Worker가 구 ANALYZE/EXECUTE 큐에서 실행 | 필요한 기능을 옮기고 구 큐를 종료한 뒤 제거. 단순 미사용 파일이 아님 |
| 현재 분석 그래프 | `access/phase2_graph.py`의 `build_analysis_graph` | 승인 분석의 기준으로 유지. 최종적으로 `access/graph.py` 또는 `analysis.py` 등으로 정리 |
| 현재 실행 그래프 | `access/phase2_execution.py`의 `build_execution_graph` | 유지하고 `execution.py` 등으로 정리. 분석과 실행 분리는 승인 전후의 업무 단계 분리이므로 중복 아님 |
| 해석과 선택 | `phase2_intent.py`가 기존 `planner.interpret`를 호출, `phase2_selection.py`가 `planner.contains_token`, `planner.model`을 사용 | 의도 해석·LLM 생성·선택 로직을 책임별로 분리. `planner.py`를 통째로 삭제할 수 없음 |
| 기존에만 있는 기능 | `graph.py`의 `gather_node`/`collect_evidence`, `planner.investigate`, `answering.py`, `response_context.py`, `permission_proposal.py` | 기술 문제 진단·사용법 안내·추가 도구 조사·답변 검토 중 현재 제품에 필요한 기능을 먼저 선정해 이식. 동등한 기능이라고 가정하지 않음 |
| 승인 보고서 | `phase2_review.py`, `approval-review-guide.md`, `common/phase2_reporting.py`, `rag/unlockops_rag/approval.py` | 최근 근거 선택·review_facts·예산 영향·출처 검증 보강 유지. 단계명만 업무명으로 정리 |

현재 새 그래프의 GUIDE 경로는 신청·승인·규정·정책·예산 문의로 제한된다. 기존 그래프의 일반 기술 안내·진단과 같은 범위가 아니다. 기존 `graph.py` 제거 전에 이 기능을 계속 제공할지 팀 기준을 정하고, 유지하는 기능은 새 경로에서 동작하도록 해야 한다.

또한 사람의 승인 대기는 현재 Spring이 관리한다. 구 그래프의 `interrupt`/`Command(resume=...)` 방식을 새 흐름에 다시 추가할 필요는 없다. 분석·실행 작업 자체의 체크포인트와 재전달 처리는 계속 필요하다.

완료 기준: Worker가 구 그래프를 import하지 않는다. 승인 분석과 승인 후 실행만 연결되며, 유지하기로 한 기존 기능과 현재 RAG 보고서 보강이 사라지지 않는다.

**4. 회수 에이전트**

회수 그래프는 `agent/unlockops/reclaim/graph.py` 하나다. 승인처럼 구/신 회수 그래프가 두 벌 남은 상태가 아니다.

| 대상 | 현재 역할 | 권장 작업 |
|---|---|---|
| `reclaim/graph.py` | 실행 context·고정 정책·전체 페이지·알림 이력 조회와 후보 설명 | 유지. 승인 그래프와 합치지 않음 |
| `common/phase2.py`, `phase2_tools.py`, `phase2_runtime.py`, `phase2_reporting.py` | 회수도 쓰는 계약·도구 제한·오류·이벤트·보고서 | 공통 계약·런타임·보고서 모듈로 정리하고 승인/회수 import를 함께 변경 |
| `common/models.ToolFailure` | 현재 회수도 사용하는 공통 예외 | 구 승인 모델 파일 제거 전에 공통 예외로 추출 |
| `backend/.../phase2/reclaim/` | 스냅샷·서버 판정·결과 저장·필수 알림·스케줄 | 백엔드 회수 업무로 유지. 디렉터리 이름만 정리할 수 있음 |

완료 기준: 고정 스냅샷, 전체 조회 확인, 부분 결과 보존, UNKNOWN 추가 확인, 중복 알림 방지, 서버의 최종 완료 판정이 유지된다. 실제 권한 말소는 이번 구조 정리로 추가되지 않는다.

**5. Worker와 MCP**

네 업무 담당자가 따로 파일만 지우면 끊어지는 공통 실행 영역이므로 담당자를 별도로 지정한다.

| 대상 | 현재 분리 | 권장 작업 |
|---|---|---|
| `worker/unlockops_worker/__main__.py` | 구 그래프 import·resume·구 결과 발행과 신규 `run_job` 처리를 모두 보유 | 현 작업 라우팅만 유지. 구 Job/Result/Plan 및 interrupt 전용 분기를 종료 |
| `worker/unlockops_worker/phase2.py` | v1/v2 파서, 신규 작업 실행·체크포인트·결과 재사용 | 공통 업무 실행 모듈로 정리. 새 실행기 전체를 삭제하는 대상 아님 |
| 큐 | `analysis`, `execution`, `v2.analysis`, `v2.execution` 동시 소비 | 현 큐만 사용하도록 통일. 이미 있는 v2 큐 이름을 유지해도 됨 |
| 서버의 결과 수신 | `AgentResultsListener`가 구 `AgentResultService`와 신규 `Phase2Results`로 분기, `JobService`와 `Phase2Jobs`가 병존 | 현 결과·작업 계약으로 통일. outbox/inbox와 발행 확인·재전달을 유지 |
| MCP 등록 | `business.py`, `policy.py`가 구 도구를 정의하고 `phase2_business.register`/`phase2_policy.register`를 추가 | 서버 실행 진입점은 유지하면서 현재 승인·회수·정책 도구만 등록. 두 파일 자체를 삭제하면 서버가 사라짐 |
| MCP 백엔드 어댑터 | `Phase2Backend`가 `BackendClient`를 상속 | 공통 HTTP·인증·오류 처리와 업무 API 호출을 분리해 유지. 구 API별 메서드만 제거 후보 |

현재 새 업무 도구는 `get_access_request_context`, `assess_access_request`, `execute_access_plan`, `verify_access_plan`, `get_reclaim_check_context`, `list_revocation_candidates`, `get_reclaim_notification_history`, `search_workflow_policy`, `read_workflow_policy`다.

교체 전에 구 큐의 대기·미승인 메시지, 구 outbox 미발행 작업, 구 승인 대기 요청을 확인하고 처리 기준을 정한다. 구 대기 메시지를 새 계약으로 그대로 해석하지 않는다. 과거 기록 보존만 필요하다면 실행 가능한 구 그래프 전체 대신 읽기 호환 계층만 남길 수 있다.

**6. 공통 계약과 가드레일**

| 대상 | 현재 상태 | 권장 작업 |
|---|---|---|
| 업무 모델 | `common/models.py`의 구 Job/Plan/Result와 `common/phase2.py`의 새 업무 계약 | 최신 업무 계약으로 통일. 구 파일의 `Intent`, `ToolFailure` 등 현재 사용되는 항목을 먼저 분리 |
| 도구 계약 | `common/contracts.py`가 구 INPUTS/OUTPUTS에 `phase2_tools`의 registry를 합침 | 현재 도구 registry 하나로 정리. MCPTools·ContractMCP가 이 검증기를 사용하므로 파일 통째 삭제 금지 |
| 가드레일 | `common/tools.py`의 구 `ScopedTools`와 `common/phase2_runtime.py`의 `Phase2Tools` | 최신 작업별 범위 제한을 기준으로 통합. 읽기/쓰기 분리·작업/계획 고정·호출 한도·재시도·입출력 검증 유지 |
| 공통 연결 | `common/tools.py`의 `MCPTools`, `common/settings.py` | 신규 승인·회수에서도 사용하므로 유지. 구 workflow 전용 클래스·설정만 따로 제거 |
| 생성 계약 | `common/phase2.py` → JSON Schema·Java `Phase2Types`·TS 타입과 생성 스크립트 | 생성 원본 하나 유지. 이름·위치를 바꾸면 생성기와 import도 함께 수정. 생성 결과를 언어별로 수동 재작성하지 않음 |

`schema_version=2`, `/api/v2/problems`, `plan_version`, 정책 revision은 단계별 소스 디렉터리와 다르다. 단일 실행 경로에서도 계약·승인 회차·정책 이력 버전은 필요하다. phase2 정리를 이유로 버전을 1로 되돌리거나 해시 내용을 줄이지 않는다.

**7. 정책과 데이터**

| 대상 | 현재 분리 | 권장 작업 |
|---|---|---|
| 정책 조회 진입점 | `data/policy_corpus.md`, `data/company-a-access-matrix.md` 기반 v1 조회와 DB 회사별 정책 revision 조회 | 운영 조회는 회사·업무·해시가 고정되는 현 경로로 통일. 구 문서에만 있는 필요한 진단 근거는 별도 검토 후 반영 |
| 검색 엔진 | `DocumentIndex`와 `RevisionIndex` | 정책 저장·검색 진입점을 정리. `revisions.py`도 `search.py`의 `features`, `cosine`을 사용하므로 검색 모듈 통째 삭제 금지 |
| 원문과 생성 묶음 | 수신 `policies/policy_corpus.md`, 회사별 v2/v3 파일 | 원문과 회사별 생성 결과는 역할이 달라 단순 중복이 아님. 원문 ID·조항·버전과 묶음 해시를 보존 |
| 시연 초기화 | Compose의 `DEMO_PHASE2_SEED_PATH`는 `seed.sql`만 가리킴. 최신 자료는 `apply.sql`·`apply-v4.sql`까지 필요 | 최신 시연 데이터 준비를 한 명령·명확한 진입점으로 묶기. 구 revision을 덮어쓰는 방식으로 통합하지 않음 |
| 권한과 영수증 | 기존 `permissions`·`grant_receipts` 계열과 현 `entitlements`·`access_assignments`·`access_execution_receipts` 계열 | 신규 쓰기는 현 권한 항목·할당 구조로 통일. 기존 데이터/FK/조회 사용을 확인한 뒤 별도 migration으로 정리 여부 결정 |
| baseline과 이력 | `catalog.json`·`seed.sql`의 기준 데이터, 정책/가격 revision 1·2·3 | 실행 경로와 비교·이력 데이터를 구분. baseline 보존은 구 실행 코드 보존을 요구하지 않음 |

`users`, `departments`, `resources`, `problems`, 예산, outbox/inbox 등은 이미 공유한다. DB 전체가 v1/v2 두 벌인 것은 아니다. 적용된 Flyway V1~V8은 수정·삭제하지 않고 이후 migration으로 변경한다. 과거 승인 계획·정책 해시·회수 스냅샷도 보존한다.

**8. 테스트와 문서**

| 대상 | 현재 상태 | 권장 작업 |
|---|---|---|
| 기존 그래프 검사 | `agent/tests/test_scenarios.py`, `test_checkpoint.py`, `test_harness.py` 등 | 보장하던 동작을 현재 그래프에서 검사하도록 옮긴 뒤 구 import를 제거 |
| 기존 MCP·HTTP 통합 | `mcp/tests/test_api_graph.py`, `test_backend_client.py`, `tests/test_live_stack.py` | 현 API·도구·승인 단계 기준으로 변경. 구 경로 통과만으로 현재 흐름 검증을 대신하지 않음 |
| 신규 계약·업무 검사 | `test_phase2_contracts.py`, `test_phase2_workflows.py`, `test_phase2_approval_review.py`, 백엔드 현 계약·업무 테스트 | 유지하고 구조 변경에 맞춰 import·이름 정리. 신규 보고서 보강 검사도 포함 |
| 평가 실행 | `scripts/evaluate_phase2.py`, `scripts/phase2/`, `.github/workflows/phase2-evaluation.yml` | 현재 기준 통합 평가로 유지. v4 기대값과 baseline 비교용 데이터의 역할을 명시 |
| 프론트 검사 | 구 요청 화면·접수·안내 완료 검사와 `frontend/tests/phase2.test.mjs` | 현 화면으로 이전하며 동일 의미의 검사 중복을 정리 |
| 실행·계약 문서 | 루트/영역별 README, `docs/architecture.md`, `docs/contracts/`, `contracts/phase2/`, `IMPLEMENTATION.md` | 사용자용 실행 절차·API·상태 명세를 현재 경로로 통일. 과거 구현 기록은 이력으로 유지 |

실제 결함(CR-03 과거 회수 결과 표시, CR-04 조회 시점 불일치, CR-05 승인 대기 목록 누락)은 구조 정리와 별도 항목으로 추적한다. 폴더 이동만으로 해결됐다고 처리하지 않는다. 테스트가 없어지면서 이 문제들의 확인 지점도 사라지지 않도록 한다.

**함께 정해야 하는 기준과 권장 순서**

| 순서 | 공동 작업 | 종료 조건 |
|---|---|---|
| 1 | 현재 업무 계약·API·기능 범위 확정 | 다단계 승인·회수 계약을 기준으로 고정. 기존 진단·가이드 중 유지할 기능 명시 |
| 2 | 공통 의존성 추출 | LLM 생성, Intent/ToolFailure, MCP 연결, 도구 검증·가드레일의 공용 위치 확정 |
| 3 | 각 담당 영역 통합 | 프론트·서버·승인·회수의 import와 호출자가 새 기준만 사용. 필요한 기존 기능 이식 |
| 4 | 구 작업 실행 경로 종료 | 구 큐/outbox/승인 대기 건 처리 확인. Worker·MCP·서버의 v1 실행 연결 종료 |
| 5 | 제거와 이름 정리 | 구 전용 코드 제거. phase2 파일명을 업무명으로 정리하고 생성 계약·평가·문서 동시 갱신 |
| 6 | 한 흐름으로 검증 | 프론트 빌드, 핵심 회귀 검사, 승인/보류/재개/실행/검증·회수 smoke/full 확인 |

먼저 계약과 공통 의존성을 합의하고, 같은 파일을 여러 담당자가 동시에 덮어쓰지 않도록 Worker/MCP·계약 담당자를 지정한다. 사용자·DB 이력·메시지 계약 버전 보존과 구 업무 실행 코드 유지 여부는 별도로 판단한다.
