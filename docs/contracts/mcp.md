# MCP 도구 계약

원본은 `agent/unlockops/common/tool_contracts.py`입니다. `common/contracts.py`의 단일 registry와 검증기를 Agent·두 MCP 서버가 공유합니다.
각 MCP 도구는 호출 전 입력, 호출 후 출력과 공통 오류를 검사합니다. 알려지지 않은 필드·작업 ID·계획 변경을 허용하지 않습니다.

| 도구 | 필수 입력 | 출력 |
|---|---|---|
| get_access_request_context | problem_id | 회사·요청·직원 사실·권한 항목·정책·workflow |
| assess_access_request | problem_id, job_event_id, entitlement_id | 판정·이유·계획·근거, 선택 review_facts |
| execute_access_plan | problem_id, job_event_id, plan_hash, idempotency_key | 실행 영수증 또는 PLAN_REVIEW_REQUIRED |
| verify_access_plan | 같은 실행 식별자 | receipt_exists, verification_ok, source |
| get_reclaim_check_context | run_id | 고정 snapshot_id/as_of/expected_count/정책 |
| list_revocation_candidates | run_id, policy_hash, 선택 cursor | 고정 페이지와 next_cursor |
| get_reclaim_notification_history | run_id, assignment_ids | 해당 스냅샷의 후보 발생 건·알림 이력 |
| search_workflow_policy | task_type, work_id, query, 선택 source_hash/limit | source_hash, evidence, retrieval_mode |
| read_workflow_policy | task_type, work_id, source_hash, 선택 article | 동일 revision의 정확 근거 |

execute_access_plan만 승인 후 쓰기 도구입니다. 힌트는 실제 승인·범위 검사를 대신하지 않습니다.
`WorkflowTools`가 승인 분석/실행/회수별 허용 목록을 검사합니다. 분석·회수 도구는 권한을 변경하지 않습니다.
MCP의 WorkflowBackend는 서버 HTTP를 호출하고 공통 BackendClient가 서비스 인증·타임아웃·오류를 처리합니다.

오류는 `{"ok":false,"error":{"code":"...","message":"...","retryable":false,"reason":null}}` 형태입니다.
통신 장애와 일시 상태만 제한 재시도합니다. 인증·형식·범위·승인 불일치를 재시도하거나 제공자 응답 원문을 노출하지 않습니다.
도구 이름별 JSON Schema를 MCP discovery에 게시하며 런타임에도 같은 모델로 검사합니다.

review_facts는 관측 시각·선택 자원/권한·TF 자격·단가·통화·출처·잔여 예산입니다.
승인 보고서는 이 사실을 계획 금액과 대조하며 문서의 정가 예시로 채우지 않습니다. 사실이 없는 이전 응답도 처리하되 값을 추측하지 않습니다.
보고서 지침은 `agent/unlockops/access/approval-review-guide.md`, 상세 적용 범위는 [승인 RAG 점검](../rag-approval-review.md)에 있습니다.

구 직원별 조회·grant_permission·파일 정책 도구는 제거했습니다. 현재 도구만 등록하며 회수에서 승인 실행 도구를 호출할 수 없습니다.
