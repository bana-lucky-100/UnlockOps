"""State → 노드 함수 → 분기 함수 → 그래프 연결 순서로 읽는 권한 처리 흐름."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from .contracts import validate_output
from .models import Plan, Result, ToolFailure
from .planner import interpret, investigate
from .rules import evaluate, FORBIDDEN
from .settings import settings
from .tools import ScopedTools


# 1. State: 각 노드가 읽고 갱신하는 작업 기록. total=False는 단계별 필드 추가를 허용한다.
class AgentState(TypedDict, total=False):
    job: dict  # 백엔드가 확정한 요청자·플랫폼·원문
    intent: dict  # 요청 해석 결과

    profile: dict  # 직원의 직무·직급·소속
    resource: dict  # 확정한 대상 자원
    membership: dict  # 실제 TF 소속
    current: dict  # 현재 보유 권한
    budget: dict | None
    evidence: list[dict]  # 규정 원문과 조회 사실
    evidence_complete: bool

    plan: dict | None  # 사람에게 승인받을 실행 계획
    result: dict
    execution_key: str  # 승인 후 받은 멱등 실행 키
    attempts: int
    execution_error: dict | None
    verify_attempts: int
    verified: bool | None
    verify_error: dict | str | None  # 이전 체크포인트의 문자열 오류도 읽는다.

    events: list[dict]  # 노드 진행 이력
    tool_calls: int
    optional_tool_calls: int


# 노드에서 함께 사용하는 진행 기록·결과 작성 함수.
def event(state: AgentState, node: str, **details) -> list[dict]:
    """기존 이벤트에 새 진행 기록을 붙인다."""
    return state.get("events", []) + [{"node": node, **details}]


async def pause(seconds):
    """재시도 전에 지정한 시간만큼 비동기로 기다린다."""
    await asyncio.sleep(seconds)


def outcome(state, status, code, message, role="", verified=None):
    """판정·실행 결과를 백엔드가 받는 공통 응답 형식으로 만든다."""
    plan = None
    if role and state.get("resource"):
        plan = Plan(
            problem_id=state["job"]["problem_id"],
            requester_id=state["job"]["requester_id"],
            platform=state["job"]["platform"],
            resource_id=state["resource"]["id"],
            resource_key=state["resource"]["external_id"],
            requested_role=role,
        )
    return Result(
        status=status,
        reasonCode=code,
        summary=message,
        diagnosis=message,
        proposal=message,
        evidence=state.get("evidence", []),
        nextAction={
            "WAITING_APPROVAL": "지정 승인자의 검토 및 승인",
            "MANUAL_REVIEW": "담당자 수동 검토",
            "REJECTED": "부서장에게 예산 증액 요청"
            if code == "BUDGET_INSUFFICIENT"
            else "사유 확인 후 별도 절차 안내",
            "FAILED": "담당자가 실패 내역 확인",
            "DONE": "처리 완료",
        }.get(status, ""),
        plan=plan,
        verification_ok=verified,
        agent_mode=settings.mode,
    ).model_dump(mode="json")


# 2. 노드: 입력 State에서 필요한 값을 읽고, 바뀐 필드만 dict로 돌려준다.
async def interpret_node(state: AgentState) -> dict:
    """사용자의 증상을 구조화한다. 데모는 규칙, LLM 모드는 모델을 사용한다."""
    job = state["job"]
    intent = await interpret(job["contents"], job["platform"])
    return {"intent": intent.model_dump(), "events": event(state, "interpret", mode=settings.mode)}


def scope_node(state: AgentState) -> dict:
    """단일 플랫폼 요청으로 확정할 수 없으면 조회 전에 수동 검토로 끝낸다."""
    if not state["intent"]["out_of_scope"]:
        return {"events": event(state, "scope", accepted=True)}
    result = outcome(
        state,
        "MANUAL_REVIEW",
        "REQUEST_OUT_OF_SCOPE",
        "선택한 플랫폼의 단일 권한 요청으로 범위를 확정할 수 없어 담당자 검토가 필요합니다.",
    )
    return {"result": result, "plan": None, "events": event(state, "scope", accepted=False)}


async def context_node(state: AgentState, *, tools) -> dict:
    """MCP로 직원을 조회하고, 사용자가 명시한 자원 하나를 확정한다."""
    job = state["job"]
    scoped = ScopedTools(tools, job["requester_id"], job["platform"])
    profile = await scoped.read("get_employee_profile", {"employee_id": job["requester_id"]})
    # 모델이 만든 이름 대신 사용자 원문으로 대상 자원을 찾는다.
    resolved = await scoped.read(
        "resolve_resource", {"platform": job["platform"], "hint": job["contents"]}
    )
    matches = resolved.get("matches", [])
    resource = matches[0] if len(matches) == 1 else {}
    return {
        "profile": profile,
        "resource": resource,
        "tool_calls": scoped.calls,
        "events": event(state, "context", resource_count=len(matches), tools=scoped.trace),
    }


async def gather_node(state: AgentState, *, tools) -> dict:
    """필수 사실·규정을 먼저 모은 후 LLM의 선택 조회를 수행한다."""
    job, resource = state["job"], state["resource"]
    scoped = ScopedTools(tools, job["requester_id"], job["platform"], resource.get("id"))
    scoped.calls = state.get("tool_calls", 0)
    evidence = []
    evidence_complete = True
    platform_policy = {
        "GITHUB": "POL-03",
        "JIRA": "POL-04",
        "SLACK": "POL-05",
        "NOTION": "POL-08",
    }
    required = ["POL-01", "POL-07", platform_policy[job["platform"]]]
    if resource.get("access_scope") == "TF":
        required.append("POL-02")
    if resource.get("access_scope") == "SEAT":
        required.append("POL-06")
    search = await scoped.read(
        "search_policy", {"query": job["contents"], "platform": job["platform"]}
    )
    evidence.extend(search.get("hits", []))
    for doc_id in required:
        document = await scoped.read("read_policy", {"doc_id": doc_id})
        if not any(c.get("doc_id") == doc_id and c.get("text") for c in document.get("chunks", [])):
            evidence_complete = False
        evidence.extend(document["chunks"])
    membership, current, budget = {}, {}, None
    investigation = "skipped"
    if resource:
        # 실제 소속·현재 권한은 RAG에서 추측하지 않고 정확한 ID로 조회한다.
        args = {"employee_id": job["requester_id"], "resource_id": resource["id"]}
        membership = await scoped.read("get_tf_membership", args)
        current = await scoped.read("get_current_permissions", args)
        if resource["access_scope"] == "SEAT":
            budget = (await scoped.read("check_budget", {"employee_id": job["requester_id"]}))[
                "budget"
            ]
        rules = await scoped.read("search_access_rules", {**args, "query": job["contents"]})
        evidence.extend(rules.get("hits", []))
        # 검색 유사도가 낮더라도 필수 규정 원문은 확보한다.
        for doc_id in ("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07"):
            chunks = (await scoped.read("read_access_rule", {"doc_id": doc_id}))["chunks"]
            if not any(c.get("doc_id") == doc_id and c.get("text") for c in chunks):
                evidence_complete = False
            evidence.extend(chunks)
        evidence.append(
            {
                "kind": "employee_facts",
                "department": state["profile"]["department_name"],
                "grade": state["profile"]["job_grade"],
                "job_family": state["profile"]["job_family"],
                "tf_member": membership.get("member", False),
                "current_role": current.get("role"),
                "maximum_role": rules.get("maximum_role"),
                "budget": budget,
            }
        )
        # 필수 조회가 끝난 뒤에만 LLM 선택 조회 예산을 사용한다.
        investigation = await investigate(scoped, state["profile"], resource, job["contents"])
    unique = {x.get("chunk_id", str(i)): x for i, x in enumerate(evidence)}
    return {
        "membership": membership,
        "current": current,
        "budget": budget,
        "evidence": list(unique.values()),
        "tool_calls": scoped.calls,
        "optional_tool_calls": scoped.optional_calls,
        "evidence_complete": evidence_complete,
        "events": event(state, "collect_evidence", tools=scoped.trace, investigation=investigation),
    }


def judge_node(state: AgentState) -> dict:
    """수집한 사실과 코드의 정책 규칙으로 승인·거절·수동 검토를 판정한다."""
    explicit = state["intent"]["requested_role"]
    if not state.get("evidence_complete"):
        status, code, message, role = (
            "MANUAL_REVIEW",
            "MISSING_SOURCE_EVIDENCE",
            "필수 규정 근거를 확인할 수 없어 담당자 검토가 필요합니다.",
            "",
        )
    elif explicit.lower() in FORBIDDEN:
        status, code, message, role = (
            "REJECTED",
            "FORBIDDEN_ADMIN",
            "Admin·Owner·전체 액세스는 자동 부여하지 않습니다. IT 보안팀에 문의해야 합니다.",
            "",
        )
    elif not state["resource"]:
        status, code, message, role = (
            "MANUAL_REVIEW",
            "RESOURCE_NOT_UNIQUE",
            "대상 자원을 하나로 확정할 수 없어 담당자 검토가 필요합니다.",
            "",
        )
    else:
        verdict = evaluate(
            state["profile"],
            state["resource"],
            state["membership"],
            state["current"],
            state["budget"],
            explicit,
        )
        status, code, message, role = verdict.status, verdict.code, verdict.message, verdict.role
    result = outcome(
        state, status, code, message, role, True if code == "ALREADY_HAS_ACCESS" else None
    )
    return {
        "result": result,
        "plan": result["plan"],
        "events": event(state, "judge", status=status, reason_code=code),
    }


def approval_node(state: AgentState) -> dict:
    """같은 계획에 대한 승인과 실행 키를 받을 때까지 그래프를 멈춘다."""
    # 재개하면 함수 처음부터 실행되므로, 여기서는 권한 변경 같은 부수 효과를 만들지 않는다.
    response = interrupt(
        {
            "type": "APPROVAL",
            "plan": state["plan"],
            "plan_hash": Plan.model_validate(state["plan"]).digest(),
        }
    )
    expected = Plan.model_validate(state["plan"]).digest()
    if not response.get("approved") or response.get("plan_hash") != expected:
        raise ToolFailure("INVALID_APPROVAL", "Approval does not match the checkpoint plan")
    if not response.get("idempotency_key"):
        raise ToolFailure("INVALID_APPROVAL", "Missing execution key")
    return {
        "execution_key": response["idempotency_key"],
        "attempts": 0,
        "verify_attempts": 0,
        "events": event(state, "approval_recorded"),
    }


async def execute_node(state: AgentState, *, tools) -> dict:
    """승인된 계획만 실행한다. 재시도에도 같은 실행 키를 사용한다."""
    attempt = state.get("attempts", 0) + 1
    error = None
    try:
        validate_output(
            "grant_permission",
            await tools.call(
                "grant_permission",
                {
                    "problem_id": state["job"]["problem_id"],
                    "idempotency_key": state["execution_key"],
                },
            ),
        )
    except ToolFailure as exc:
        error = {"code": exc.code, "retryable": exc.retryable}
    return {
        "attempts": attempt,
        "execution_error": error,
        "events": event(state, "execute", attempt=attempt, error=error),
    }


async def retry_node(state: AgentState) -> dict:
    """일시적인 실행 오류에는 짧게 대기한 뒤 재시도한다."""
    await pause(min(2 ** state["attempts"], 5))
    return {"events": event(state, "retry", next_attempt=state["attempts"] + 1)}


async def verify_node(state: AgentState, *, tools) -> dict:
    """부여 응답과 별개로 실제 권한을 다시 조회해 반영 여부를 확인한다."""
    plan = state["plan"]
    verified, error = None, None
    try:
        response = validate_output(
            "verify_permission",
            await tools.call(
                "verify_permission",
                {
                    "employee_id": plan["requester_id"],
                    "resource_id": plan["resource_id"],
                    "requested_role": plan["requested_role"],
                },
            ),
        )
        verified = response["verified"]
    except ToolFailure as exc:
        error = {"code": exc.code, "retryable": exc.retryable}
    return {
        "verified": verified,
        "verify_error": error,
        "verify_attempts": state.get("verify_attempts", 0) + 1,
        "events": event(state, "verify", verified=verified, error=error),
    }


async def verify_retry_node(state: AgentState) -> dict:
    """권한 반영 지연 또는 일시적 조회 오류이면 확인만 다시 한다."""
    await pause(2)
    return {"events": event(state, "verify_retry")}


def finish_node(state: AgentState) -> dict:
    """실행·검증 상태를 최종 결과로 바꾼다."""
    if state.get("execution_error"):
        code, status = state["execution_error"]["code"], "FAILED"
        message = f"권한 부여가 완료되지 않았습니다. 실행 시도: {state['attempts']}회."
    elif state.get("verified") is True:
        code, status, message = "VERIFIED", "DONE", "권한 부여 후 실제 반영을 확인했습니다."
    else:
        error = state.get("verify_error")
        code = (error["code"] if isinstance(error, dict) else error) or "VERIFICATION_FAILED"
        status, message = (
            "FAILED",
            "권한 변경 후 실제 반영을 확인하지 못했습니다. 담당자 검토가 필요합니다.",
        )
    result = outcome(
        state, status, code, message, state["plan"]["requested_role"], state.get("verified")
    )
    return {"result": result, "events": event(state, "finish", status=status, reason_code=code)}


# 3. 분기 함수: State를 읽고 다음 노드의 이름만 반환한다.
def route_after_scope(state: AgentState) -> str:
    """범위 밖 요청은 종료하고 지원 대상 요청은 사실 조회로 보낸다."""
    if state["intent"]["out_of_scope"]:
        return END
    return "context"


def route_after_judge(state: AgentState) -> str:
    """승인이 필요한 판정만 승인 노드로 보내고 나머지는 종료한다."""
    if state["result"]["status"] == "WAITING_APPROVAL":
        return "approval"
    return END


def route_after_execute(state: AgentState) -> str:
    """부여 성공은 검증으로, 재시도 가능한 실패는 한도 내 재실행으로 보낸다."""
    error = state.get("execution_error")
    if not error:
        return "verify"
    if error["retryable"] and state["attempts"] < settings.max_execution_attempts:
        return "retry"
    return "finish"


def route_after_verify(state: AgentState) -> str:
    """반영 확인·영구 오류·횟수 한도에 따라 다음 노드를 고른다."""
    if (
        state.get("verified") is True
        or state["verify_attempts"] >= settings.max_verification_attempts
    ):
        return "finish"
    error = state.get("verify_error")
    if error and (not isinstance(error, dict) or not error.get("retryable")):
        return "finish"
    # verified=false이면 제한 횟수 안에서 반영 여부를 재조회한다.
    return "verify_retry"


# 4. 그래프: 노드 등록 → 연결 → 조건부 연결 → 체크포인트를 붙여 컴파일한다.
def build_graph(tools, checkpointer):
    """노드와 조건 분기를 연결하고 체크포인트로 승인 후 재개할 그래프를 만든다."""
    builder = StateGraph(AgentState)

    # partial은 공통 MCP 연결을 미리 넣어, 그래프가 state만 전달할 수 있게 한다.
    builder.add_node("interpret", interpret_node)
    builder.add_node("scope", scope_node)
    builder.add_node("context", partial(context_node, tools=tools))
    builder.add_node("gather", partial(gather_node, tools=tools))
    builder.add_node("judge", judge_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", partial(execute_node, tools=tools))
    builder.add_node("retry", retry_node)
    builder.add_node("verify", partial(verify_node, tools=tools))
    builder.add_node("verify_retry", verify_retry_node)
    builder.add_node("finish", finish_node)

    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "scope")
    builder.add_conditional_edges("scope", route_after_scope, ["context", END])
    builder.add_edge("context", "gather")
    builder.add_edge("gather", "judge")
    builder.add_conditional_edges("judge", route_after_judge, ["approval", END])

    builder.add_edge("approval", "execute")
    builder.add_conditional_edges("execute", route_after_execute, ["verify", "retry", "finish"])
    builder.add_edge("retry", "execute")
    builder.add_conditional_edges("verify", route_after_verify, ["finish", "verify_retry"])
    builder.add_edge("verify_retry", "verify")
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer)
