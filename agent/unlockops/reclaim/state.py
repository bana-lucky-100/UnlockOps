"""Shared checkpoint state for the Phase 2 reclaim roles."""
from typing import TypedDict

class ReclaimState(TypedDict, total=False):
    job: dict
    context: dict
    policy_evidence: list[dict]
    targets: list[dict]
    before_report_targets: list[dict]
    report_payload: dict
    history: list[dict]
    scan_complete: bool
    error: dict
    skip: bool
    result_event: dict
    events: list[dict]
