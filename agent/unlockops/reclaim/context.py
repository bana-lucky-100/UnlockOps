"""Load the immutable reclaim scope and reject stale jobs before scanning."""
from ..common.workflow_contracts import ReclaimJob
from ..common.tool_contracts import ReclaimContext
from ..common.runtime import guarded
from ..common.models import ToolFailure
from ..common.settings import settings

@guarded
async def load_context(state, *, tools):
    job = ReclaimJob.model_validate(state["job"])
    context = ReclaimContext.model_validate(await tools.call("get_reclaim_check_context", {"run_id": str(job.run_id)}, retry=True))
    if context.run_id != job.run_id:
        raise ToolFailure("RUN_SCOPE", "Unexpected run")
    if context.job_event_id != job.event_id:
        return {"skip": True}
    if context.expected_count > settings.max_reclaim_candidates:
        return {"context": context.model_dump(mode="json"), "scan_complete": False,
                "error": {"code": "SCAN_LIMIT"}}
    return {"context": context.model_dump(mode="json")}
