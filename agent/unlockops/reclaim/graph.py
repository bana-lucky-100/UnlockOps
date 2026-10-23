"""Read-only reclaim graph: frozen context -> full scan -> history -> report -> event."""
import json
from functools import partial
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from ..common.workflow_contracts import ReclaimJob, ReclaimEvent, ReclaimRunView, ReclaimCandidate, CandidatePage
from ..common.tool_contracts import ReclaimContext, PolicyResult, NotificationHistory
from ..common.runtime import WorkflowTools, guarded, event_id, failure_event
from ..common.reporting import report
from ..common.models import ToolFailure
from ..common.settings import settings


class ReclaimState(TypedDict, total=False):
    job: dict
    context: dict
    policy_evidence: list[dict]
    targets: list[dict]
    history: list[dict]
    scan_complete: bool
    error: dict
    skip: bool
    result_event: dict
    events: list[dict]


@guarded
async def load_context(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = ReclaimContext.model_validate(await tools.call("get_reclaim_check_context", {"run_id": str(job.run_id)}, retry=True))
    if context.run_id != job.run_id:
        raise ToolFailure("RUN_SCOPE", "Unexpected run")
    if context.job_event_id != job.event_id:
        return {"skip": True}
    if context.expected_count > settings.max_reclaim_candidates:
        raise ToolFailure("SCAN_LIMIT", "Snapshot exceeds baseline scan limit")
    return {"context": context.model_dump(mode="json")}


@guarded
async def retrieve_policy(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = state["context"]["context"]
    scope = {"task_type": "RECLAIM_SCAN", "work_id": str(job.run_id), "source_hash": context["policy_hash"]}
    found = PolicyResult.model_validate(await tools.call("search_workflow_policy", {**scope, "query": "TF 종료 미사용 30일 다른 활성 TF 유지 승인 퇴사자 좌석 회수 후보", "limit": 5}, retry=True))
    exact = PolicyResult.model_validate(await tools.call("read_workflow_policy", {**scope, "article": ""}, retry=True))
    policy = context["policy"]
    if found.source_hash != context["policy_hash"] or exact.source_hash != context["policy_hash"] or not exact.evidence:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Reclaim policy hash differs")
    for e in [*found.evidence, *exact.evidence]:
        if e.source_hash != policy["source_hash"] or e.doc_id != policy["doc_id"] or e.version != str(policy["revision"]) or e.text not in policy["content"]:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Reclaim citation is not in the frozen policy")
    return {"policy_evidence": [e.model_dump(mode="json") for e in exact.evidence]}


@guarded
async def scan_all_pages(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = ReclaimContext.model_validate(state["context"])
    cursor, cursors, ids, items = None, set(), set(), []
    try:
        # Whole scan is one checkpointed node. On crash, reread the immutable pages instead of combining partial versions.
        while True:
            page = CandidatePage.model_validate(await tools.call("list_revocation_candidates", {
                "run_id": str(job.run_id), "policy_hash": context.context.policy_hash, "cursor": cursor}, retry=True))
            if page.run_id != job.run_id or page.snapshot_id != context.snapshot_id or page.as_of != context.as_of or page.expected_count != context.expected_count:
                raise ToolFailure("SNAPSHOT_MISMATCH", "Candidate page belongs to another snapshot")
            for item in page.items:
                if item.assignment_id in ids:
                    raise ToolFailure("DUPLICATE_ASSIGNMENT", "Duplicate assignment across pages")
                for e in item.policy_evidence:
                    policy = context.context.policy
                    if e.source_hash != policy.source_hash or e.doc_id != policy.doc_id or e.version != str(policy.revision) or e.text not in policy.content:
                        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Candidate policy differs from snapshot")
                ids.add(item.assignment_id)
                items.append(item.model_dump(mode="json"))
            if len(items) > context.expected_count or len(items) > settings.max_reclaim_candidates:
                raise ToolFailure("SCAN_LIMIT", "Candidate count exceeds the declared bound")
            if page.next_cursor is None:
                break
            if not page.items or page.next_cursor in cursors:
                raise ToolFailure("INVALID_PAGE_CURSOR", "Empty/cyclic candidate page")
            cursors.add(page.next_cursor)
            cursor = page.next_cursor
        if len(items) != context.expected_count:
            raise ToolFailure("INCOMPLETE_SCAN", "Missing snapshot rows")
        if len(json.dumps(items, ensure_ascii=False).encode()) > settings.max_result_bytes - 10_000:
            raise ToolFailure("SCAN_LIMIT", "Result exceeds baseline message limit")
    except (ToolFailure, ValueError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, ToolFailure) else "INVALID_TOOL_OUTPUT"
        return {"targets": items, "scan_complete": False, "error": {"code": code}}
    return {"targets": items, "scan_complete": True}


@guarded
async def notification_history(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    ids = [c["assignment_id"] for c in state["targets"]]
    history = []
    for offset in range(0, len(ids), 200):
        batch = ids[offset:offset+200]
        response = NotificationHistory.model_validate(await tools.call("get_reclaim_notification_history", {"run_id": str(job.run_id), "assignment_ids": batch}, retry=True))
        if any(str(row.assignment_id) not in batch for row in response.items):
            raise ToolFailure("RUN_SCOPE", "Notification history includes another assignment")
        history.extend(x.model_dump(mode="json") for x in response.items)
    # Delivery and episode identity are finalized by Spring; history is context, not permission to send.
    return {"history": history}


@guarded
async def compose_reports(state):
    targets = []
    notified = {row['assignment_id'] for row in state.get('history', [])
                if row['candidate_status'] == 'PENDING_REVIEW' and row.get('notified_at')}
    generated = 0
    for index, original in enumerate(state["targets"]):
        item = dict(original)
        if (item['candidate_status'] == 'PENDING_REVIEW' and not item['review_required']
                and not item.get('notified_at') and item['assignment_id'] not in notified
                and generated < settings.max_model_steps // 2):
            generated += 1
            facts = {k: item[k] for k in ("platform", "candidate_status", "candidate_reason_code", "exclusion_reason_code", "review_required", "cost_impact", "action_taken")}
            text, mode = await report(facts, state["policy_evidence"], item["explanation"])
            item.update(explanation=text, generation_mode=mode)
        targets.append(ReclaimCandidate.model_validate(item).model_dump(mode="json"))
    return {"targets": targets}


def finish(state):
    if state.get("skip"):
        return {"result_event": {}}
    job = ReclaimJob.model_validate(state["job"])
    if state.get("error"):
        event = failure_event(job, state["error"]["code"])
        context = state.get('context')
        if context:
            event['result'].update(snapshot_id=context['snapshot_id'], as_of=context['as_of'])
            # Bound failed responses retain only checked rows and never trigger notifications.
            event['targets'] = state.get('targets', [])
            event['result']['message'] = '일부만 조회되었거나 점검을 완료하지 못했습니다. 부분 결과는 알림 대상이 아닙니다.'
            if len(json.dumps(event, ensure_ascii=False).encode()) > settings.max_result_bytes:
                event['targets'] = []
        return {"result_event": ReclaimEvent.model_validate(event).model_dump(mode='json')}
    context = state["context"]
    needs_review = sum(c["review_required"] for c in state["targets"])
    result = ReclaimRunView(schema_version=2, run_id=job.run_id,
        status="EXECUTING", reason_code="SCAN_IN_PROGRESS",
        message="전체 점검 결과와 추가 확인 항목을 서버에 전달합니다.",
        snapshot_id=context["snapshot_id"], as_of=context["as_of"], scan_complete=True, needs_review_count=needs_review)
    event = ReclaimEvent(schema_version=2, event_id=event_id(job), job_event_id=job.event_id,
        run_id=job.run_id, event_type="RECLAIM_CHECKED", result=result, targets=state["targets"]).model_dump(mode="json")
    if len(json.dumps(event, ensure_ascii=False).encode()) > settings.max_result_bytes:
        event = failure_event(job, "SCAN_LIMIT")
    return {"result_event": event}


def build_graph(tools, job, checkpointer=None):
    scoped = WorkflowTools(tools, job)
    graph = StateGraph(ReclaimState)
    nodes = [("context", partial(load_context, tools=scoped)), ("policy", partial(retrieve_policy, tools=scoped)),
             ("scan", partial(scan_all_pages, tools=scoped)), ("history", partial(notification_history, tools=scoped)), ("report", compose_reports)]
    for name, node in nodes:
        graph.add_node(name, node)
    graph.add_node("finish", finish)
    graph.add_edge(START, "context")
    for i, (name, _) in enumerate(nodes):
        next_node = nodes[i+1][0] if i+1 < len(nodes) else "finish"
        graph.add_conditional_edges(name, lambda s, next_node=next_node: "finish" if s.get("error") or s.get("skip") else next_node)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
