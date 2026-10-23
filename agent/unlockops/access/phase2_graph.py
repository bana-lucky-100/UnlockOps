"""v2 analysis graph. Human approval state and continuation belong to Spring."""
from functools import partial
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from ..common.phase2 import AccessJob, AccessView, ApprovalStep, GrantPlanV2
from ..common.phase2_tools import AccessContext, Assessment, PolicyResult
from ..common.phase2_runtime import Phase2Tools, guarded, access_event, failure_event
from ..common.phase2_reporting import report
from ..common.models import ToolFailure
from ..common.settings import settings
from .phase2_intent import interpret_v4 as interpret
from .phase2_selection import select_entitlement


class AccessState(TypedDict, total=False):
    job: dict
    context: dict
    intent: dict
    entitlement_id: str
    least_privilege: bool
    assessment: dict
    evidence: list[dict]
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
    intent = await interpret(p["contents"], p["platform"])
    if intent.out_of_scope:
        raise ToolFailure("OUT_OF_SCOPE", "Request spans unsupported operations")
    return {"intent": intent.model_dump()}


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
        if e.source_hash != policy["source_hash"] or e.doc_id != policy["doc_id"] or e.version != str(policy["revision"]) or e.text not in policy["content"]:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Unsupported policy citation")
        evidence[e.article] = e.model_dump(mode="json")
    return {"evidence": list(evidence.values())}


@guarded
async def assess(state, *, tools):
    if state["intent"]["request_type"] == "GUIDE":
        # Only policy/process guidance is supported by the baseline policy corpus.
        question = state["context"]["problem"]["contents"]
        if not any(word in question for word in ("신청", "승인", "규정", "정책", "예산")):
            raise ToolFailure("OUT_OF_SCOPE", "Technical guide source is not available")
        return {"assessment": {"status": "DONE", "reason": "RAG_GUIDANCE", "message": "권한 신청은 회사 규정과 예산을 확인한 뒤 지정된 순서로 승인받아야 합니다.", "plan": None, "evidence": state["evidence"]}}
    entitlement, least = await select_entitlement(state["context"], state["intent"])
    job = AccessJob.model_validate(state["job"])
    assessment = Assessment.model_validate(await tools.call("assess_access_request", {
        "problem_id": str(job.problem_id), "job_event_id": str(job.event_id), "entitlement_id": entitlement}))
    if assessment.plan:
        plan, p = assessment.plan, state["context"]["problem"]
        if str(plan.problem_id) != p["id"] or str(plan.requester_id) != p["requester_id"] or str(plan.company_id) != p["company_id"] or str(plan.entitlement_id) != entitlement or plan.platform != p["platform"]:
            raise ToolFailure("PLAN_CHANGED", "Assessment plan identity differs")
        if not any(e.source_hash == x["source_hash"] and e.doc_id == x["doc_id"] and e.version == x["version"] for e in assessment.evidence for x in state["evidence"]):
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Assessment and retrieval revisions differ")
    return {"assessment": assessment.model_dump(mode="json"), "entitlement_id": entitlement, "least_privilege": least}


@guarded
async def compose_report(state):
    assessment = state["assessment"]
    plan = assessment.get("plan")
    template = assessment["message"]
    facts = {"status": assessment["status"], "reason_code": assessment["reason"]}
    if plan:
        template += (f" 예상 월 비용은 {plan['monthly_amount']} {plan['currency']}이며, 총 {len(plan['approver_ids'])}단계 승인이 필요합니다. "
                     "1차 담당자는 업무 필요성을, 이후 담당자는 정책·허용 범위·비용을 검토해 주세요. 아직 권한은 변경되지 않았습니다.")
        facts.update(monthly_amount=plan["monthly_amount"], currency=plan["currency"], cost_basis=plan["cost_basis"], total_steps=len(plan["approver_ids"]))
    text, mode = await report(facts, state["evidence"], template)
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
    scoped = Phase2Tools(tools, job)
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
