"""Validate all candidate pages and read notification history; never reclaim seats."""
import json
from copy import deepcopy
from ..common.workflow_contracts import ReclaimJob, CandidatePage
from ..common.tool_contracts import ReclaimContext, NotificationHistory
from ..common.runtime import guarded
from ..common.models import ToolFailure
from ..common.settings import settings
from .policy import _policy_sections
from .verification import verify_candidate

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
            # Reject inconsistent page metadata before retaining any rows from it.
            if len(items) + len(page.items) > min(context.expected_count, settings.max_reclaim_candidates):
                raise ToolFailure("SCAN_LIMIT", "Candidate count exceeds the declared bound")
            if page.next_cursor is not None and (
                not page.items or not page.next_cursor.strip() or len(page.next_cursor) > 500
                or page.next_cursor in cursors
            ):
                raise ToolFailure("INVALID_PAGE_CURSOR", "Empty/cyclic candidate page or invalid cursor")
            for item in page.items:
                if item.assignment_id in ids:
                    raise ToolFailure("DUPLICATE_ASSIGNMENT", "Duplicate assignment across pages")
                verify_candidate(item, context, sections)
                ids.add(item.assignment_id)
                items.append(item.model_dump(mode="json"))
            if page.next_cursor is None:
                break
            cursors.add(page.next_cursor)
            cursor = page.next_cursor
        if len(items) != context.expected_count:
            raise ToolFailure("INCOMPLETE_SCAN", "Missing snapshot rows")
        if len(json.dumps(items, ensure_ascii=False).encode()) > settings.max_result_bytes - 10_000:
            raise ToolFailure("SCAN_LIMIT", "Result exceeds the reclaim message limit")
    except (ToolFailure, ValueError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, ToolFailure) else "INVALID_TOOL_OUTPUT"
        return {"targets": items, "verified_targets": deepcopy(items),
                "scan_complete": False, "error": {"code": code}}
    return {"targets": items, "verified_targets": deepcopy(items), "scan_complete": True}


@guarded
async def notification_history(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    ids = [c["assignment_id"] for c in state["targets"]]
    history = []
    episodes = set()
    for offset in range(0, len(ids), 200):
        batch = ids[offset:offset+200]
        response = NotificationHistory.model_validate(await tools.call("get_reclaim_notification_history", {"run_id": str(job.run_id), "assignment_ids": batch}, retry=True))
        if any(str(row.assignment_id) not in batch for row in response.items):
            raise ToolFailure("RUN_SCOPE", "Notification history includes another assignment")
        for row in response.items:
            identity = (row.assignment_id, row.episode_id)
            if identity in episodes:
                raise ToolFailure("INVALID_TOOL_OUTPUT", "Duplicate notification episode")
            episodes.add(identity)
        history.extend(x.model_dump(mode="json") for x in response.items)
    # Delivery and episode identity are finalized by Spring; history is context, not permission to send.
    return {"history": history}
