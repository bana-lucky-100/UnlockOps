"""Approval-specific grounding and narration boundaries; no paid model or live database."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from unlockops.common import reporting
from unlockops.common.tool_contracts import Assessment
from unlockops.common.settings import settings
from unlockops.access.review import review_guidance, review_input
from unlockops_rag.approval import approval_evidence, source_role
from unlockops_rag.revisions import revision_index

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads((ROOT / "contracts/phase2/examples/vectors.json").read_text())["valid"][0]["payload"]


def policy():
    text = (ROOT / "data/phase2/policies/company-a-policy-v3.md").read_text()
    return dict(company_id=PLAN["company_id"], policy_id=PLAN["policy_id"], revision=3,
                doc_id="P2-A-POLICY", content=text, source_hash=hashlib.sha256(text.encode()).hexdigest())


def evidence(platform="SNOWFLAKE"):
    return revision_index(**policy(), platform=platform).read()


def state():
    return {
        "context": {
            "problem": {"platform": "SNOWFLAKE", "contents": "연락처가 포함된 사용자 요청", "requester_id": PLAN["requester_id"]},
            "requester": {"employment_status": "ACTIVE", "job_family": "DEV", "job_grade": "사원", "login_id": "never-send", "email": "private@example.com"},
            "facts": [{"account_exists": True, "license_active": True, "job_function": "ANALYST", "source_reference": "private-provider-id"}],
            "entitlements": [{"id": PLAN["entitlement_id"], "code": "ANALYST", "kind": "ROLE", "name": "분석 웨어하우스"}],
        },
        "assessment": {"status": "WAITING_APPROVAL", "reason": "ELIGIBLE", "message": "정책 판정을 확인했습니다.", "plan": deepcopy(PLAN),
            "review_facts": {"checked_at": "2026-10-23T11:00:00+09:00", "resource_name": "분석 웨어하우스", "entitlement_code": "ANALYST", "entitlement_kind": "ROLE",
                "access_scope": "GENERAL", "tf_member": None, "monthly_amount": PLAN["monthly_amount"], "currency": PLAN["currency"], "remaining_budget": "150.00", "price_source_kind": "SYNTHETIC_CONTRACT"},
            "evidence": evidence()},
        "entitlement_id": PLAN["entitlement_id"], "least_privilege": False, "evidence": approval_evidence(evidence(), "SNOWFLAKE"),
    }


def test_approval_references_cover_v4_without_reclaim_or_other_platform_leakage():
    cases = json.loads((ROOT / "data/phase2/scenarios-v4.json").read_text())["scenarios"]
    for case in cases:
        if case["id"].startswith("R-"):
            continue
        kind = "SEAT" if case["platform"] == "GITHUB" and case["id"] != "B-02" else "ROLE"
        rows = approval_evidence(evidence(case["platform"]), case["platform"], kind)
        for expected in case["expected_evidence"]:
            assert any(all(token in r["article"] for token in expected) for r in rows), case["id"]
        assert not any("회수" in r["article"] or r["article"].startswith("POL-06") and "제5조" in r["article"] for r in rows)
    github = evidence("GITHUB")
    assert not any(r["article"].startswith(("POL-03", "GH-OFF-01", "GH-OFF-02")) for r in approval_evidence(github, "GITHUB", "SEAT"))
    assert not any(r["article"].startswith("GH-OFF-03") for r in approval_evidence(github, "GITHUB", "ROLE"))
    assert source_role("GH-OFF-03 | GITHUB | 2026-10-22 | 핵심 요약") == "PRODUCT_REFERENCE"


def test_report_uses_server_budget_and_keeps_private_fields_and_unknown_tf_out():
    s = state()
    facts, template = review_input(s)
    assert facts["projected_budget"] == "30.00"
    assert "150.00 → 30.00 USD" in template
    assert "시연 가정" in template and "실제 청구액이 아닙니다" in template
    assert "TF 구성원 자격을 확인" not in template
    raw = json.dumps(facts, ensure_ascii=False)
    for private in (PLAN["requester_id"], "private@example.com", "never-send", "private-provider-id", "연락처가 포함된 사용자 요청"):
        assert private not in raw
    s["assessment"].pop("review_facts")
    facts, template = review_input(s)
    assert facts["review_facts"] is None and "projected_budget" not in facts
    assert "개별 조회 값은 전달되지 않았습니다" in template


def test_budget_hold_does_not_claim_a_charge_or_an_approval_route():
    s = state()
    s["assessment"].update(status="ON_HOLD", reason="BUDGET_INSUFFICIENT", message="예산 부족으로 보류", plan=None)
    s["assessment"]["review_facts"]["remaining_budget"] = "10.00"
    facts, template = review_input(s)
    assert facts["projected_budget"] == "-110.00"
    assert "실제 차감 전" in template and "예산 확보 후" in template
    assert "단계의 순차 승인" not in template
    s["assessment"]["plan"] = deepcopy(PLAN)
    s["assessment"].update(status="WAITING_APPROVAL", reason="ELIGIBLE")
    s["assessment"]["review_facts"]["monthly_amount"] = "999.00"
    with pytest.raises(ValidationError, match="Report facts differ"):
        Assessment.model_validate(s["assessment"])


@pytest.mark.parametrize("fault", ["insufficient", "tf_unknown", "false_hold"])
def test_observed_facts_cannot_contradict_the_assessment(fault):
    assessment = state()["assessment"]
    if fault == "insufficient":
        assessment["review_facts"]["remaining_budget"] = "10.00"
    elif fault == "tf_unknown":
        assessment["review_facts"]["access_scope"] = "TF"
    else:
        assessment.update(status="ON_HOLD", reason="BUDGET_INSUFFICIENT", plan=None)
    with pytest.raises(ValidationError, match="contradict"):
        Assessment.model_validate(assessment)


@pytest.mark.parametrize("fault", [None, "quote", "review", "unavailable"])
async def test_approval_narration_is_grounded_and_falls_back_without_changing_facts(monkeypatch, fault):
    monkeypatch.setattr(reporting, "settings", replace(settings, mode="llm"))
    s = state()
    facts, template = review_input(s)
    calls = []
    class FakeModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self
        async def ainvoke(self, messages):
            calls.append(messages)
            if fault == "unavailable":
                raise RuntimeError("offline")
            if self.schema is reporting.Review:
                return self.schema(supported=fault != "review")
            return self.schema(explanation="근거에 따른 승인 검토 자료입니다.", source_indexes=[0],
                quotes=["없는 인용" if fault == "quote" else s["evidence"][0]["text"]])
    monkeypatch.setattr(reporting, "model", FakeModel)
    text, mode = await reporting.report(facts, s["evidence"], template, guidance=review_guidance())
    assert (text, mode) == (("근거에 따른 승인 검토 자료입니다.", "llm") if fault is None else (template, "template"))
    assert all("PRODUCT_REFERENCE" in messages[0][1] for messages in calls)
    assert facts["server_assessment"]["status"] == "WAITING_APPROVAL"
