"""Register separate v2 tools without exposing legacy writes to the reclaim agent."""
from .contracts import APPROVED_WRITE, READ_ONLY
from .phase2_backend import Phase2Backend


def register(mcp):
    repo = Phase2Backend()

    @mcp.tool(annotations=READ_ONLY)
    def get_access_request_context(problem_id: str) -> dict[str, object]:
        """승인 요청의 회사 범위 내 직무·자원·정책·현재 승인 상태를 조회합니다."""
        return repo.invoke("get_access_request_context", {"problem_id": problem_id})

    @mcp.tool(annotations=READ_ONLY)
    def assess_access_request(problem_id: str, job_event_id: str, entitlement_id: str) -> dict[str, object]:
        """현재 분석 작업의 권한 후보를 서버 정책·예산·승인 경로로 검증합니다. 승인·변경은 하지 않습니다."""
        return repo.invoke("assess_access_request", {"problem_id": problem_id, "job_event_id": job_event_id, "entitlement_id": entitlement_id})

    @mcp.tool(annotations=APPROVED_WRITE)
    def execute_access_plan(problem_id: str, job_event_id: str, plan_hash: str, idempotency_key: str) -> dict[str, object]:
        """최종 사람 승인이 끝난 계획만 서버에서 실행합니다. 작업·계획 해시·실행 키가 모두 일치해야 합니다."""
        return repo.invoke("execute_access_plan", {"problem_id": problem_id, "job_event_id": job_event_id, "plan_hash": plan_hash, "idempotency_key": idempotency_key})

    @mcp.tool(annotations=READ_ONLY)
    def verify_access_plan(problem_id: str, job_event_id: str, plan_hash: str, idempotency_key: str) -> dict[str, object]:
        """별도 요청으로 현재 모의 제공자 상태를 조회합니다. 영수증만으로 성공하지 않습니다."""
        return repo.invoke("verify_access_plan", {"problem_id": problem_id, "job_event_id": job_event_id, "plan_hash": plan_hash, "idempotency_key": idempotency_key})

    @mcp.tool(annotations=READ_ONLY)
    def get_reclaim_check_context(run_id: str) -> dict[str, object]:
        """회수 실행에 고정된 스냅샷·시각·조회 개수·정책과 규칙을 읽습니다."""
        return repo.invoke("get_reclaim_check_context", {"run_id": run_id})

    @mcp.tool(annotations=READ_ONLY)
    def list_revocation_candidates(run_id: str, policy_hash: str, cursor: str | None = None) -> dict[str, object]:
        """고정된 스냅샷의 다음 페이지를 읽습니다. 제외·유지·미확인 행도 포함하며 권한을 회수하지 않습니다."""
        return repo.invoke("list_revocation_candidates", {"run_id": run_id, "policy_hash": policy_hash, "cursor": cursor})

    @mcp.tool(annotations=READ_ONLY)
    def get_reclaim_notification_history(run_id: str, assignment_ids: list[str]) -> dict[str, object]:
        """해당 실행 스냅샷에 포함된 할당의 후보 발생 건·전달 이력을 조회합니다."""
        return repo.invoke("get_reclaim_notification_history", {"run_id": run_id, "assignment_ids": assignment_ids})

    return {fn.__name__: fn for fn in (get_access_request_context, assess_access_request, execute_access_plan, verify_access_plan,
                                      get_reclaim_check_context, list_revocation_candidates, get_reclaim_notification_history)}
