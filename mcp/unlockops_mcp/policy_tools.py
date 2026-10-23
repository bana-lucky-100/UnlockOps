"""Resolve policy identity from a work item, then retrieve that immutable revision."""
from unlockops.common.models import ToolFailure
from unlockops_rag.revisions import revision_index
from .workflow_backend import WorkflowBackend
from .contracts import READ_ONLY


def scoped_index(repo, task_type, work_id, source_hash):
    platform = None
    if task_type == "ACCESS_REQUEST":
        context = repo.invoke("get_access_request_context", {"problem_id": work_id})
        platform = context['problem']['platform']
        policies = context["policies"]
        if len({p["policy_id"] for p in policies}) != 1:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy family is absent or ambiguous")
        choices = [p for p in policies if not source_hash or p["source_hash"] == source_hash]
        if not choices:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy revision is unavailable")
        policy = max(choices, key=lambda p: p["revision"])
    elif task_type == "RECLAIM_SCAN":
        context = repo.invoke("get_reclaim_check_context", {"run_id": work_id})
        policy = context["context"]["policy"]
        if source_hash and policy["source_hash"] != source_hash:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Frozen policy revision differs")
    else:
        raise ToolFailure("INVALID_TOOL_INPUT", "Unsupported policy work type")
    return revision_index(policy["company_id"], policy["policy_id"], policy["revision"],
                          policy["doc_id"], policy["source_hash"], policy["content"], platform)


def register(mcp):
    repo = WorkflowBackend()

    @mcp.tool(annotations=READ_ONLY)
    def search_workflow_policy(task_type: str, work_id: str, query: str, limit: int = 5, source_hash: str | None = None) -> dict[str, object]:
        """요청/회수 실행에 속한 회사 정책 버전만 검색합니다. 다른 회사·파일 경로를 지정할 수 없습니다."""
        index = scoped_index(repo, task_type, work_id, source_hash)
        return {"source_hash": index.source_hash, "evidence": index.search(query, limit), "retrieval_mode": "local-tfidf"}

    @mcp.tool(annotations=READ_ONLY)
    def read_workflow_policy(task_type: str, work_id: str, source_hash: str, article: str = "") -> dict[str, object]:
        """서버가 고정한 정책 해시의 조항을 정확히 읽습니다. 검색에서 놓친 필수 근거도 확인합니다."""
        index = scoped_index(repo, task_type, work_id, source_hash)
        return {"source_hash": index.source_hash, "evidence": index.read(article), "retrieval_mode": "exact"}

    return {fn.__name__: fn for fn in (search_workflow_policy, read_workflow_policy)}
