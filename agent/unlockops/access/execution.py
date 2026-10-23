"""Execution starts from Spring's approved plan, independently of analysis checkpoints."""
import asyncio
from functools import partial
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from ..common.workflow_contracts import AccessJob, AccessView, GrantPlanV2
from ..common.tool_contracts import AccessContext, ExecutionReceipt, Verification
from ..common.runtime import WorkflowTools, guarded, access_event, failure_event
from ..common.models import ToolFailure
from ..common.settings import settings


class ExecutionState(TypedDict, total=False):
    job: dict
    context: dict
    receipt: dict
    verification: dict
    error: dict
    skip: bool
    result_event: dict
    events: list[dict]


def arguments(job):
    return {"problem_id": str(job.problem_id), "job_event_id": str(job.event_id), "plan_hash": job.plan_hash, "idempotency_key": job.idempotency_key}


@guarded
async def load_approved(state, *, tools):
    job = AccessJob.model_validate(state["job"])
    context = AccessContext.model_validate(await tools.call("get_access_request_context", {"problem_id": str(job.problem_id)})).model_dump(mode="json")
    p, workflow = context["problem"], context["workflow"]
    if p["id"] != str(job.problem_id):
        raise ToolFailure("REQUEST_SCOPE", "Unexpected execution request")
    if p["active_job_event_id"] != str(job.event_id) or workflow["status"] not in {"EXECUTING", "DONE"}:
        return {"skip": True}
    if p["plan"] is None:
        raise ToolFailure("PLAN_CHANGED", "Approved plan is missing")
    plan = GrantPlanV2.model_validate(p["plan"])
    if plan.digest() != job.plan_hash or p["approved_plan_hash"] != job.plan_hash or p["idempotency_key"] != job.idempotency_key or plan.problem_id != job.problem_id or str(plan.requester_id) != p["requester_id"] or str(plan.company_id) != p["company_id"]:
        raise ToolFailure("PLAN_CHANGED", "Execution does not match the approved plan")
    if not workflow["approval_steps"] or any(s["status"] != "APPROVED" for s in workflow["approval_steps"]) or [s["approver_id"] for s in workflow["approval_steps"]] != [str(x) for x in plan.approver_ids]:
        raise ToolFailure("APPROVAL_REQUIRED", "All bound approvals are required")
    return {"context": context}


@guarded
async def execute(state, *, tools):
    job = AccessJob.model_validate(state["job"])
    receipt = ExecutionReceipt.model_validate(await tools.call("execute_access_plan", arguments(job), retry=True))
    if not receipt.executed:
        # Admission already transitioned to MANUAL_REVIEW on the server. Never retry under another key.
        context = AccessContext.model_validate(await tools.call("get_access_request_context", {"problem_id": str(job.problem_id)}))
        if context.workflow.status != "MANUAL_REVIEW":
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Admission failure did not enter review")
        return {"skip": True}
    plan = state["context"]["problem"]["plan"]
    if receipt.problem_id != job.problem_id or receipt.plan_hash != job.plan_hash or receipt.idempotency_key != job.idempotency_key or receipt.charged_amount != plan["monthly_amount"] or receipt.currency != plan["currency"]:
        raise ToolFailure("INVALID_TOOL_OUTPUT", "Grant receipt does not match the approved execution")
    return {"receipt": receipt.model_dump(mode="json")}


@guarded
async def verify(state, *, tools):
    job = AccessJob.model_validate(state["job"])
    # Always a new tool/API read. No context/analysis cache can establish verification.
    result = None
    for attempt in range(settings.max_verification_attempts):
        result = Verification.model_validate(await tools.call("verify_access_plan", arguments(job), retry=True))
        if result.problem_id != job.problem_id or not result.receipt_exists:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Verification identity/receipt is invalid")
        if result.verification_ok:
            break
        if attempt + 1 < settings.max_verification_attempts:
            await asyncio.sleep(1)
    return {"verification": result.model_dump(mode="json")}


def finish(state):
    if state.get("skip"):
        return {"result_event": {}}
    job = AccessJob.model_validate(state["job"])
    if state.get("error"):
        return {"result_event": failure_event(job, state["error"]["code"])}
    ok = state["verification"]["verification_ok"]
    workflow = dict(state["context"]["workflow"])
    workflow.update(status="DONE" if ok else "FAILED", reason_code="VERIFIED" if ok else "VERIFICATION_FAILED",
        result_type="ACCESS_VERIFIED" if ok else None, verification_ok=ok, current_step=None,
        message="권한 부여 후 실제 접근 상태를 확인했습니다." if ok else "권한 부여 후 조회 결과가 승인 계획과 일치하지 않습니다.")
    return {"result_event": access_event(job, AccessView.model_validate(workflow))}


def build_execution_graph(tools, job, checkpointer=None):
    scoped = WorkflowTools(tools, job)
    graph = StateGraph(ExecutionState)
    nodes = [("context", load_approved), ("execute", execute), ("verify", verify)]
    for name, node in nodes:
        graph.add_node(name, partial(node, tools=scoped))
    graph.add_node("finish", finish)
    graph.add_edge(START, "context")
    for i, (name, _) in enumerate(nodes):
        next_node = nodes[i+1][0] if i+1 < len(nodes) else "finish"
        graph.add_conditional_edges(name, lambda s, next_node=next_node: "finish" if s.get("error") or s.get("skip") else next_node)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
