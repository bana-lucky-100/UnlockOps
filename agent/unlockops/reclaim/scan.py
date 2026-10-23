"""Validate all candidate pages and read notification history; never reclaim seats."""
import json
from ..common.phase2 import ReclaimJob, CandidatePage
from ..common.phase2_tools import ReclaimContext, NotificationHistory
from ..common.phase2_runtime import guarded
from ..common.models import ToolFailure
from ..common.settings import settings
from .policy import _policy_sections

@guarded
async def scan_all_pages(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = ReclaimContext.model_validate(state["context"])
    sections = _policy_sections(context.context.policy.content)
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
                    cited = [text for heading, text in sections.items()
                             if heading == e.article or heading.startswith(e.article + " ")]
                    if (e.source_hash != policy.source_hash or e.doc_id != policy.doc_id
                            or e.version != str(policy.revision) or not e.text.strip()
                            or not any(e.text in text for text in cited)):
                        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Candidate policy differs from snapshot")
                ids.add(item.assignment_id)
                items.append(item.model_dump(mode="json"))
            if len(items) > context.expected_count or len(items) > settings.phase2_max_candidates:
                raise ToolFailure("SCAN_LIMIT", "Candidate count exceeds the declared bound")
            if page.next_cursor is None:
                break
            if not page.items or page.next_cursor in cursors:
                raise ToolFailure("INVALID_PAGE_CURSOR", "Empty/cyclic candidate page")
            cursors.add(page.next_cursor)
            cursor = page.next_cursor
        if len(items) != context.expected_count:
            raise ToolFailure("INCOMPLETE_SCAN", "Missing snapshot rows")
        if len(json.dumps(items, ensure_ascii=False).encode()) > settings.phase2_max_result_bytes - 10_000:
            raise ToolFailure("SCAN_LIMIT", "Result exceeds the reclaim message limit")
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
