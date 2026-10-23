"""Verify that report narration preserves the checked reclaim facts."""
from ..common.workflow_contracts import ReclaimCandidate
from ..common.runtime import guarded
from ..common.models import ToolFailure


@guarded
async def verify_reports(state):
    """Only explanation text and generation mode may differ after narration."""
    originals = state["before_report_targets"]
    supplied = state["targets"]
    if len(originals) != len(supplied):
        raise ToolFailure("REPORT_FACT_MISMATCH", "Narration changed the number of scan rows")
    mutable = {"explanation", "generation_mode"}
    for original, current in zip(originals, supplied):
        before = ReclaimCandidate.model_validate(original).model_dump(mode="json", exclude=mutable)
        after = ReclaimCandidate.model_validate(current).model_dump(mode="json", exclude=mutable)
        if before != after:
            raise ToolFailure("REPORT_FACT_MISMATCH", "Narration changed a verified decision or fact")
    return {}
