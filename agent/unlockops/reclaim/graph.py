"""Wire the Phase 2 reclaim roles; Spring finalizes storage and notification status."""
import json
from functools import partial
from langgraph.graph import StateGraph, START, END
from ..common.phase2 import ReclaimJob, ReclaimEvent, ReclaimRunView
from ..common.phase2_runtime import Phase2Tools, event_id
from ..common.settings import settings
from .state import ReclaimState
from .context import load_context
from .policy import retrieve_policy
from .scan import scan_all_pages, notification_history
from .reporting import compose_reports, verify_reports, build_failure_event, report_from_event


def finish(state):
    if state.get("skip"):
        return {"result_event": {}}
    job = ReclaimJob.model_validate(state["job"])
    if state.get("error"):
        event = build_failure_event(job, state, state["error"]["code"], max_bytes=settings.phase2_max_result_bytes)
        return {"result_event": event, "report_payload": report_from_event(event)}
    context = state["context"]
    needs_review = sum(c["review_required"] for c in state["targets"])
    result = ReclaimRunView(schema_version=2, run_id=job.run_id,
        status="EXECUTING", reason_code="SCAN_IN_PROGRESS",
        message="전체 점검 결과와 추가 확인 항목을 서버에 전달합니다.",
        snapshot_id=context["snapshot_id"], as_of=context["as_of"], scan_complete=True, needs_review_count=needs_review)
    event = ReclaimEvent(schema_version=2, event_id=event_id(job), job_event_id=job.event_id,
        run_id=job.run_id, event_type="RECLAIM_CHECKED", result=result, targets=state["targets"]).model_dump(mode="json")
    if len(json.dumps(event, ensure_ascii=False).encode()) > settings.phase2_max_result_bytes:
        event = build_failure_event(job, state, "SCAN_LIMIT", max_bytes=settings.phase2_max_result_bytes)
    return {"result_event": event, "report_payload": report_from_event(event)}


def build_graph(tools, job, checkpointer=None):
    scoped = Phase2Tools(tools, job)
    graph = StateGraph(ReclaimState)

    def role(nodes):
        subgraph = StateGraph(ReclaimState)
        for name, node in nodes:
            subgraph.add_node(name, node)
        subgraph.add_edge(START, nodes[0][0])
        for i, (name, _) in enumerate(nodes):
            next_node = nodes[i+1][0] if i+1 < len(nodes) else END
            subgraph.add_conditional_edges(name, lambda s, next_node=next_node: END if s.get("error") or s.get("skip") else next_node)
        return subgraph.compile()

    nodes = [("context", partial(load_context, tools=scoped)),
             ("policy_review", role([("policy", partial(retrieve_policy, tools=scoped))])),
             ("candidate_review", role([("scan", partial(scan_all_pages, tools=scoped)),
                                         ("history", partial(notification_history, tools=scoped))])),
             ("report_writer", role([("report", compose_reports), ("verify", verify_reports)]))]
    for name, node in nodes:
        graph.add_node(name, node)
    graph.add_node("finish", finish)
    graph.add_edge(START, "context")
    for i, (name, _) in enumerate(nodes):
        next_node = nodes[i+1][0] if i+1 < len(nodes) else "finish"
        graph.add_conditional_edges(name, lambda s, next_node=next_node: "finish" if s.get("error") or s.get("skip") else next_node)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
