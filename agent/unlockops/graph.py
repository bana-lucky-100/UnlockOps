"""요청 해석 → 근거 수집 → 권한 검토 → 사람 승인 → 실행·확인을 연결하는 그래프."""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .models import Plan, Result, Status, ToolFailure
from .planner import interpret, investigate
from .permission_proposal import assess_permission
from .rules import FORBIDDEN
from .settings import settings
from .tools import ScopedTools


class AgentState(TypedDict, total=False):
    job: dict
    intent: dict
    profile: dict
    resource: dict
    membership: dict
    current: dict
    budget: dict | None
    evidence: list[dict]
    plan: dict
    result: dict
    execution_key: str
    attempts: int
    execution_error: dict | None
    verify_attempts: int
    verified: bool | None
    verify_error: str | None
    events: list[dict]
    tool_calls: int
    evidence_complete: bool
    permission_proposal: dict | None  # LLM의 권한·이유·근거 ID. 실제 실행 계획과 별도로 기록한다.


def event(state, node, **details):
    return state.get("events", []) + [{"node": node, **details}]


async def pause(seconds):
    await asyncio.sleep(seconds)


def outcome(state, status, code, message, role="", verified=None):
    plan = None
    if role and state.get("resource"):
        plan = Plan(problem_id=state["job"]["problem_id"], requester_id=state["job"]["requester_id"],
                    platform=state["job"]["platform"], resource_id=state["resource"]["id"],
                    resource_key=state["resource"]["external_id"], requested_role=role)
    return Result(status=status, reasonCode=code, summary=message, diagnosis=message,
                  proposal=message, evidence=state.get("evidence", []), nextAction={
                      "WAITING_APPROVAL": "지정 승인자의 검토 및 승인", "MANUAL_REVIEW": "담당자 수동 검토",
                      "REJECTED": "부서장에게 예산 증액 요청" if code == "BUDGET_INSUFFICIENT" else "사유 확인 후 별도 절차 안내",
                      "FAILED": "담당자가 실패 내역 확인", "DONE": "처리 완료",
                  }.get(status, ""), plan=plan, verification_ok=verified,
                  agent_mode=settings.mode).model_dump(mode="json")


def build_graph(tools, checkpointer):
    async def parse(state):
        job = state["job"]
        intent = await interpret(job["contents"], job["platform"])
        return {"intent": intent.model_dump(), "events": event(state, "interpret", mode=settings.mode)}

    async def context(state):
        job = state["job"]
        scoped = ScopedTools(tools, job["requester_id"], job["platform"])
        profile = await scoped.read("get_employee_profile", {"employee_id": job["requester_id"]})
        # Never use a model-invented hint to resolve an unmentioned project.
        resolved = await scoped.read("resolve_resource", {"platform": job["platform"], "hint": job["contents"]})
        matches = resolved.get("matches", [])
        resource = matches[0] if len(matches) == 1 else {}
        return {"profile": profile, "resource": resource, "tool_calls": scoped.calls,
                "events": event(state, "context", resource_count=len(matches), tools=scoped.trace)}

    async def gather(state):
        job, resource = state["job"], state["resource"]
        scoped = ScopedTools(tools, job["requester_id"], job["platform"], resource.get("id"))
        scoped.calls = state.get("tool_calls", 0)
        evidence = []
        evidence_complete = True
        required = ["POL-01", "POL-07", {"GITHUB": "POL-03", "JIRA": "POL-04", "SLACK": "POL-05", "NOTION": "POL-08"}[job["platform"]]]
        if resource.get("access_scope") == "TF": required.append("POL-02")
        if resource.get("access_scope") == "SEAT": required.append("POL-06")
        search = await scoped.read("search_policy", {"query": job["contents"], "platform": job["platform"]})
        evidence.extend(search.get("hits", []))
        for doc_id in required:
            document = await scoped.read("read_policy", {"doc_id": doc_id})
            if not any(c.get("doc_id") == doc_id and c.get("text") for c in document.get("chunks", [])):
                evidence_complete = False
            evidence.extend(document["chunks"])
        membership, current, budget = {}, {}, None
        if resource:
            await investigate(scoped, state["profile"], resource, job["contents"])
            args = {"employee_id": job["requester_id"], "resource_id": resource["id"]}
            membership = await scoped.read("get_tf_membership", args)
            current = await scoped.read("get_current_permissions", args)
            if resource["access_scope"] == "SEAT":
                budget = (await scoped.read("check_budget", {"employee_id": job["requester_id"]}))["budget"]
            rules = await scoped.read("search_access_rules", {**args, "query": job["contents"]})
            evidence.extend(rules.get("hits", []))
            # Exact source sections are required even when vector recall is low.
            for doc_id in ("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07"):
                chunks = (await scoped.read("read_access_rule", {"doc_id": doc_id}))["chunks"]
                if not any(c.get("doc_id") == doc_id and c.get("text") for c in chunks): evidence_complete = False
                evidence.extend(chunks)
            evidence.append({"kind": "employee_facts", "department": state["profile"]["department_name"],
                             "grade": state["profile"]["job_grade"], "job_family": state["profile"]["job_family"],
                             "tf_member": membership.get("member", False), "current_role": current.get("role"),
                             "maximum_role": rules.get("maximum_role"), "budget": budget})
        unique = {x.get("chunk_id", str(i)): x for i,x in enumerate(evidence)}
        return {"membership": membership, "current": current, "budget": budget,
                "evidence": list(unique.values()), "tool_calls": scoped.calls,
                "evidence_complete": evidence_complete,
                "events": event(state, "collect_evidence", tools=scoped.trace)}

    async def judge(state):
        """권한 검토 결과를 기존 응답과 승인 계획에 연결한다. 실제 변경은 execute에서만 한다."""
        explicit = state["intent"]["requested_role"]
        proposal = None
        policy_details = {}
        if not state.get("evidence_complete"):
            status, code, message, role = "MANUAL_REVIEW", "MISSING_SOURCE_EVIDENCE", "필수 규정 근거를 확인할 수 없어 담당자 검토가 필요합니다.", ""
        elif explicit.lower() in FORBIDDEN:
            status, code, message, role = "REJECTED", "FORBIDDEN_ADMIN", "Admin·Owner·전체 액세스는 자동 부여하지 않습니다. IT 보안팀에 문의해야 합니다.", ""
        elif not state["resource"]:
            status, code, message, role = "MANUAL_REVIEW", "RESOURCE_NOT_UNIQUE", "대상 자원을 하나로 확정할 수 없어 담당자 검토가 필요합니다.", ""
        else:
            # 조회한 직원 사실·RAG 근거를 권한 전용 모듈로 넘긴다.
            # 기존 요청 해석·답변 생성 프롬프트를 변경하지 않고 권한 제안 단계만 연결한다.
            verdict, proposal = await assess_permission(
                mode=settings.mode, contents=state["job"]["contents"], profile=state["profile"],
                resource=state["resource"], membership=state["membership"], current=state["current"],
                budget=state["budget"], requested_role=explicit, evidence=state["evidence"],
            )
            # 담당자가 나중에 어떤 원문과 청크로 판정했는지 추적할 수 있도록 남긴다.
            policy_details = {"source_hashes": verdict.source_hashes,
                              "sources": list(verdict.source_ids), "evidence_ids": list(verdict.evidence_ids)}
            status, code, message, role = verdict.status, verdict.code, verdict.message, verdict.role
        # 결과 큐와 실행 계획의 기존 필드 구성을 유지한다. LLM 제안 원문은 내부 상태·이력에 기록한다.
        result = outcome(state, status, code, message, role, True if code == "ALREADY_HAS_ACCESS" else None)
        return {"result": result, "plan": result["plan"],
                "permission_proposal": proposal.model_dump() if proposal else None,
                "events": event(state, "judge", status=status, reason_code=code,
                                permission_proposal=proposal.model_dump() if proposal else None, **policy_details)}

    def approval(state):
        # Keep all side effects in other nodes: interrupt nodes restart on resume.
        response = interrupt({"type": "APPROVAL", "plan": state["plan"],
                              "plan_hash": Plan.model_validate(state["plan"]).digest()})
        expected = Plan.model_validate(state["plan"]).digest()
        if not response.get("approved") or response.get("plan_hash") != expected:
            raise ToolFailure("INVALID_APPROVAL", "Approval does not match the checkpoint plan")
        if not response.get("idempotency_key"):
            raise ToolFailure("INVALID_APPROVAL", "Missing execution key")
        return {"execution_key": response["idempotency_key"], "attempts": 0, "verify_attempts": 0,
                "events": event(state, "approval_recorded")}

    async def execute(state):
        attempt = state.get("attempts", 0) + 1
        error = None
        try:
            await tools.call("grant_permission", {"problem_id": state["job"]["problem_id"],
                                                  "idempotency_key": state["execution_key"]})
        except ToolFailure as exc:
            error = {"code": exc.code, "retryable": exc.retryable}
        return {"attempts": attempt, "execution_error": error,
                "events": event(state, "execute", attempt=attempt, error=error)}

    async def retry(state):
        await pause(min(2 ** state["attempts"], 5))
        return {"events": event(state, "retry", next_attempt=state["attempts"] + 1)}

    async def verify(state):
        plan = state["plan"]
        verified, error = None, None
        try:
            response = await tools.call("verify_permission", {"employee_id": plan["requester_id"],
                "resource_id": plan["resource_id"], "requested_role": plan["requested_role"]})
            verified = bool(response["verified"])
        except ToolFailure as exc: error = exc.code
        return {"verified": verified, "verify_error": error,
                "verify_attempts": state.get("verify_attempts", 0) + 1,
                "events": event(state, "verify", verified=verified, error=error)}

    async def verify_retry(state):
        await pause(2)
        return {"events": event(state, "verify_retry")}

    def finish(state):
        if state.get("execution_error"):
            code, status = state["execution_error"]["code"], "FAILED"
            message = f"권한 부여가 완료되지 않았습니다. 실행 시도: {state['attempts']}회."
        elif state.get("verified") is True:
            code, status, message = "VERIFIED", "DONE", "권한 부여 후 실제 반영을 확인했습니다."
        else:
            code, status, message = state.get("verify_error") or "VERIFICATION_FAILED", "FAILED", "권한 변경 후 실제 반영을 확인하지 못했습니다. 담당자 검토가 필요합니다."
        result = outcome(state, status, code, message, state["plan"]["requested_role"], state.get("verified"))
        return {"result": result, "events": event(state, "finish", status=status, reason_code=code)}

    builder = StateGraph(AgentState)
    for name, fn in (("interpret",parse),("context",context),("gather",gather),("judge",judge),
                     ("approval",approval),("execute",execute),("retry",retry),("verify",verify),
                     ("verify_retry",verify_retry),("finish",finish)):
        builder.add_node(name, fn)
    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "context")
    builder.add_edge("context", "gather")
    builder.add_edge("gather", "judge")
    builder.add_conditional_edges("judge", lambda s: "approval" if s["result"]["status"] == "WAITING_APPROVAL" else END)
    builder.add_edge("approval", "execute")
    builder.add_conditional_edges("execute", lambda s: "verify" if not s.get("execution_error") else
        ("retry" if s["execution_error"]["retryable"] and s["attempts"] < settings.max_execution_attempts else "finish"))
    builder.add_edge("retry", "execute")
    builder.add_conditional_edges("verify", lambda s: "finish" if s.get("verified") is True or s["verify_attempts"] >= 3 else "verify_retry")
    builder.add_edge("verify_retry", "verify")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)
