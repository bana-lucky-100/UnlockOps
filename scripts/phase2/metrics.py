"""Summary numbers for the verification report (stdlib only; runs on the host)."""
from __future__ import annotations

import math


def percentile(values, p):
    # Nearest-rank percentile: p95 of 20 values is the 19th smallest.
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)] if ordered else None


def summarize(cases):
    access = [c for c in cases if "expected" in c]
    observed = [c for c in access if c.get("observed")]
    matched = [c for c in observed if (c["observed"]["status"], c["observed"]["reason_code"]) == (c["expected"]["status"], c["expected"]["reason_code"])]
    seconds = [c["analysis_seconds"] for c in access if "analysis_seconds" in c]
    return {
        "cases": len(cases),
        "passed": sum(c["status"] == "PASS" for c in cases),
        "access_cases": len(access),
        # Interpretation quality: the analysis outcome alone, before human approval and execution checks.
        "analysis_matched": len(matched),
        "wrong_grant_path": sum(bool(c.get("wrong_grant_path")) for c in access),
        "manual_review": sum(c["observed"]["status"] == "MANUAL_REVIEW" for c in observed),
        "analysis_seconds_p50": percentile(seconds, 50),
        "analysis_seconds_p95": percentile(seconds, 95),
        "failed": [c["id"] for c in cases if c["status"] != "PASS"],
        "analysis_mismatched": [c["id"] for c in access if c not in matched],
    }
