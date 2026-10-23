"""v2 analysis graph. Human approval state and continuation belong to Spring."""
from functools import partial
import re
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from ..common.workflow_contracts import AccessJob, AccessView, ApprovalStep, GrantPlanV2
from ..common.tool_contracts import AccessContext, Assessment, PolicyResult
from ..common.runtime import WorkflowTools, guarded, access_event, failure_event
from ..common.reporting import report
from ..common.models import ToolFailure
from unlockops_rag.approval import approval_evidence
from .intent import interpret_v4 as interpret
from .selection import entitlement_options, select_entitlement
from .review import review_guidance, review_input
from .answering import generate_answer
from .response_context import source_id


class AccessState(TypedDict, total=False):
    job: dict
    context: dict
    intent: dict
    entitlement_id: str
    least_privilege: bool
    assessment: dict
    evidence: list[dict]
    guidance_evidence: list[dict]
    report: str
    generation_mode: str
    error: dict
    skip: bool
    result_event: dict
    events: list[dict]


@guarded
async def load_context(state, *, tools):
    job = AccessJob.model_validate(state["job"])
    data = await tools.call("get_access_request_context", {"problem_id": str(job.problem_id)})
    ctx = AccessContext.model_validate(data).model_dump(mode="json")
    if ctx["problem"]["id"] != str(job.problem_id):
        raise ToolFailure("REQUEST_SCOPE", "Unexpected problem")
    if ctx["problem"]["active_job_event_id"] != str(job.event_id) or ctx["workflow"]["status"] not in {"RECEIVED", "DIAGNOSING"}:
        return {"skip": True}
    return {"context": ctx}


@guarded
async def interpret_request(state):
    p = state["context"]["problem"]
    # The existing server-bound revision supplies descriptions, not a new price/role map.
    policies = state["context"]["policies"]
    descriptions = []
    if policies and len({item["policy_id"] for item in policies}) == 1:
        policy = max(policies, key=lambda item: item["revision"])
        sections = re.split(r"(?=^## )", policy["content"], flags=re.MULTILINE)
        for section in sections:
            fields = section.split("\n", 1)[0].removeprefix("## ").split(" | ")
            if len(fields) == 4 and fields[1] in {"COMMON", p["platform"]}:
                descriptions.append({"doc_id": policy["doc_id"], "article": fields[0], "text": section})
    intent = await interpret(p["contents"], p["platform"], entitlement_options(state["context"]), descriptions)
    if intent.out_of_scope:
        raise ToolFailure("OUT_OF_SCOPE", "Request spans unsupported operations")
    return {"intent": intent.model_dump(mode="json")}


@guarded
async def retrieve_policy(state, *, tools):
    job = AccessJob.model_validate(state["job"])
    policies = state["context"]["policies"]
    if not policies or len({x["policy_id"] for x in policies}) != 1:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy family is absent or ambiguous")
    policy = max(policies, key=lambda p: p["revision"])
    scope = {"task_type": "ACCESS_REQUEST", "work_id": str(job.problem_id), "source_hash": policy["source_hash"]}
    found = PolicyResult.model_validate(await tools.call("search_workflow_policy", {**scope, "query": state["context"]["problem"]["contents"], "limit": 5}))
    exact = PolicyResult.model_validate(await tools.call("read_workflow_policy", {**scope, "article": ""}))
    if found.source_hash != policy["source_hash"] or exact.source_hash != policy["source_hash"] or not exact.evidence:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy version mismatch")
    # Exact mandatory articles supplement retrieval; all must be excerpts from the bound document.
    evidence = {}
    for e in [*found.evidence, *exact.evidence]:
        fields = e.article.split(" | ")
        if (e.source_hash != policy["source_hash"] or e.doc_id != policy["doc_id"] or e.version != str(policy["revision"])
                or not e.text.startswith(f"## {e.article}\n") or e.text not in policy["content"]
                or len(fields) == 4 and fields[1] not in {"COMMON", state["context"]["problem"]["platform"]}):
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Unsupported policy citation")
        evidence[e.article] = e.model_dump(mode="json")
    selected = approval_evidence(list(evidence.values()), state["context"]["problem"]["platform"])
    if not selected:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Approval policy is absent")
    return {"evidence": selected, "guidance_evidence": list(evidence.values())}


@guarded
async def assess(state, *, tools):
    if state["intent"]["request_type"] == "GUIDE":
        return {"assessment": {"status": "DONE", "reason": "RAG_GUIDANCE",
            "message": "확인한 문서를 바탕으로 권한·접근 절차를 안내합니다.",
            "plan": None, "evidence": state["evidence"]}}
    entitlement, least = await select_entitlement(state["context"], state["intent"])
    job = AccessJob.model_validate(state["job"])
    assessment = Assessment.model_validate(await tools.call("assess_access_request", {
        "problem_id": str(job.problem_id), "job_event_id": str(job.event_id), "entitlement_id": entitlement}))
    if assessment.plan:
        plan, p = assessment.plan, state["context"]["problem"]
        if str(plan.problem_id) != p["id"] or str(plan.requester_id) != p["requester_id"] or str(plan.company_id) != p["company_id"] or str(plan.entitlement_id) != entitlement or plan.platform != p["platform"]:
            raise ToolFailure("PLAN_CHANGED", "Assessment plan identity differs")
        policy = max(state["context"]["policies"], key=lambda p: p["revision"])
        if str(plan.policy_id) != policy["policy_id"] or plan.policy_revision != policy["revision"]:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Plan and retrieved policy revisions differ")
        if not assessment.evidence or any(
            e.source_hash != policy["source_hash"] or e.doc_id != policy["doc_id"]
            or e.version != str(policy["revision"]) or e.text not in policy["content"]
            for e in assessment.evidence
        ):
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Assessment and retrieval revisions differ")
    option = next(e for e in state["context"]["entitlements"] if e["id"] == entitlement)
    observed = assessment.review_facts
    if observed and (observed.entitlement_code != option["code"] or observed.entitlement_kind != option["kind"]):
        raise ToolFailure("INVALID_TOOL_OUTPUT", "Review facts refer to a different entitlement")
    evidence = approval_evidence(state["evidence"], state["context"]["problem"]["platform"], option["kind"], observed.access_scope if observed else None)
    if not evidence:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Approval policy is absent")
    return {"assessment": assessment.model_dump(mode="json"), "entitlement_id": entitlement, "least_privilege": least, "evidence": evidence}


@guarded
async def compose_report(state):
    # Guidance uses bound product/policy excerpts and never authorizes a grant.
    if state["intent"]["request_type"] == "GUIDE" or (
        state["intent"]["request_type"] == "TROUBLESHOOT"
        and state["assessment"]["reason"] == "ALREADY_HAS_ACCESS"
    ):
        draft, _ = await generate_answer(state)
        if draft is None:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "No supported guidance is available")
        cited = {c.chunk_id for step in draft.steps for c in step.citations}
        evidence = [e for e in state.get("guidance_evidence", state["evidence"]) if source_id(e) in cited]
        if not evidence:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Guidance citations are missing")
        text = "확인한 문서를 바탕으로 안내합니다.\n" + "\n".join(
            f"{i}. {step.text}\n근거: " + ", ".join(dict.fromkeys(c.chunk_id for c in step.citations))
            for i, step in enumerate(draft.steps, 1))
        return {"report": text, "assessment": {**state["assessment"], "reason": "RAG_GUIDANCE"}, "evidence": evidence}
    facts, template = review_input(state)
    text, mode = await report(facts, state["evidence"], template, guidance=review_guidance())
    return {"report": text, "generation_mode": mode}


def finish(state):
    if state.get("skip"):
        return {"result_event": {}}
    job = AccessJob.model_validate(state["job"])
    if state.get("error"):
        return {"result_event": failure_event(job, state["error"]["code"])}
    a = state["assessment"]
    steps = []
    if a.get("plan"):
        steps = [ApprovalStep(step=i+1, approver_id=actor, status="WAITING" if i == 0 else "PENDING") for i, actor in enumerate(a["plan"]["approver_ids"])]
    reason = "LEAST_PRIVILEGE_PROPOSED" if state.get("least_privilege") and steps else a["reason"]
    result = AccessView(schema_version=2, problem_id=job.problem_id, status=a["status"], reason_code=reason,
        message=state["report"], current_step=1 if steps else None, total_steps=len(steps), approval_steps=steps,
        plan_hash=GrantPlanV2.model_validate(a["plan"]).digest() if steps else None,
        result_type="GUIDANCE" if a["status"] == "DONE" else None)
    return {"result_event": access_event(job, result, entitlement=state.get("entitlement_id"), evidence=state["evidence"])}


def build_analysis_graph(tools, job, checkpointer=None):
    scoped = WorkflowTools(tools, job)
    graph = StateGraph(AccessState)
    nodes = [("context", partial(load_context, tools=scoped)), ("interpret", interpret_request),
             ("policy", partial(retrieve_policy, tools=scoped)), ("assess", partial(assess, tools=scoped)), ("report", compose_report)]
    for name, node in nodes:
        graph.add_node(name, node)
    graph.add_node("finish", finish)
    graph.add_edge(START, "context")
    for i, (name, _) in enumerate(nodes):
        next_node = nodes[i+1][0] if i+1 < len(nodes) else "finish"
        graph.add_conditional_edges(name, lambda s, next_node=next_node: "finish" if s.get("error") or s.get("skip") else next_node)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
