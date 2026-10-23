"""Retrieve and verify the frozen POL-06 article 5 and supporting RAG sources."""
import re
from ..common.workflow_contracts import ReclaimJob
from ..common.tool_contracts import PolicyResult
from ..common.runtime import guarded
from ..common.models import ToolFailure

def _policy_sections(content):
    return {part.splitlines()[0][3:].strip(): part.strip()
            for part in re.split(r"(?m)(?=^## )", content) if part.startswith("## ")}


def _is_reclaim_clause(article):
    return bool(re.match(r"^POL-06(?:\s*\||\s)", article) and re.search(r"제\s*5\s*조", article))


def _is_report_source(article):
    return (_is_reclaim_clause(article) or article.startswith("GH-OFF-03")
            or (article.startswith("BASELINE") and "회수" in article))


@guarded
async def retrieve_policy(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = state["context"]["context"]
    scope = {"task_type": "RECLAIM_SCAN", "work_id": str(job.run_id), "source_hash": context["policy_hash"]}
    found = PolicyResult.model_validate(await tools.call("search_workflow_policy", {**scope, "query": "TF 종료 미사용 30일 다른 활성 TF 유지 승인 퇴사자 좌석 회수 후보", "limit": 5}, retry=True))
    policy = context["policy"]
    sections = _policy_sections(policy["content"])
    required = [heading for heading in sections if _is_reclaim_clause(heading)]
    if not required:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "POL-06 article 5 is absent from the frozen policy")
    # Read the mandatory rule explicitly. Search ranking cannot replace it with
    # another policy containing similar keywords. Keep price/scope citations too.
    exact = PolicyResult.model_validate(await tools.call("read_workflow_policy", {**scope, "article": required[0]}, retry=True))
    if found.source_hash != context["policy_hash"] or exact.source_hash != context["policy_hash"] or not exact.evidence:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Reclaim policy hash differs")
    for e in [*found.evidence, *exact.evidence]:
        if (e.source_hash != policy["source_hash"] or e.doc_id != policy["doc_id"]
                or e.version != str(policy["revision"]) or sections.get(e.article) != e.text.strip()):
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Reclaim citation is not in the frozen policy")
    if not any(_is_reclaim_clause(e.article) for e in exact.evidence):
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Required reclaim clause was not returned")
    evidence = {e.article: e.model_dump(mode="json") for e in [*exact.evidence, *found.evidence] if _is_report_source(e.article)}
    return {"policy_evidence": list(evidence.values())}
