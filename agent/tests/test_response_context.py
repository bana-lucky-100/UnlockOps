"""답변 입력의 사실·출처·판정 보존과 불필요한 내부 정보 제외를 검증한다."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from conftest import FakeTools, ROOT
from test_scenarios import job
from unlockops.access import answering
from unlockops.access.answering import AnswerDraft, AnswerReview, AnswerStep, Citation
from unlockops.access.graph import build_graph, prepare_response_node
from unlockops.common.models import Plan
from unlockops.access.response_context import build_response_context
from unlockops_rag.search import DocumentIndex


def state():
    transport = FakeTools()
    return {
        "job": job("GITHUB", "payment-core push가 안 돼요"),
        "intent": {"requested_role": "Write", "request_type": "TROUBLESHOOT"},
        "profile": {**transport.profile, "name": "private-name", "password_hash": "private-password"},
        "resource": transport.resources[0], "membership": {"member": True, "leader_id": "private-leader"},
        "current": {"role": "Read"}, "maximum_role": "Write", "handling": "APPROVAL",
        "result": {"status": "WAITING_APPROVAL", "reasonCode": "ELIGIBLE", "diagnosis": "Write가 필요합니다.",
                   "nextAction": "지정 승인자 검토", "verification_ok": None},
        "plan": {"requested_role": "Write", "idempotency_key": "private-key"}, "events": [],
    }


def test_prepare_node_preserves_plan_decision_and_input_state():
    original = state()
    before = deepcopy(original)
    update = prepare_response_node(original)
    context = update["response_context"]
    assert original == before
    assert set(update) == {"response_context", "events"}
    assert context["facts"]["maximum_role"] == "Write"
    assert context["facts"]["current_role"] == "Read"
    assert context["facts"]["tf_member"] is True
    assert context["decision"]["handling"] == "APPROVAL"
    assert context["decision"]["status"] == "WAITING_APPROVAL"
    assert context["decision"]["requested_role"] == "Write"
    assert context["writing_guide"]
    payload = json.dumps(context, ensure_ascii=False)
    for private in ("private-", "requester-uuid", "head-uuid", "repo-uuid", "employee_no"):
        assert private not in payload


def test_unobserved_permissions_membership_and_ceiling_stay_unknown():
    original = state()
    original["current"] = {}
    original["membership"] = {}
    original.pop("maximum_role")
    facts = build_response_context(original)["facts"]
    assert facts["current_permissions_checked"] is False and facts["current_role"] is None
    assert facts["tf_member"] is None and facts["maximum_role"] is None
    original["current"] = {"role": None}
    original["membership"] = {"member": False}
    original["maximum_role"] = ""
    facts = build_response_context(original)["facts"]
    assert facts["current_permissions_checked"] is True and facts["current_role"] is None
    assert facts["tf_member"] is False and facts["maximum_role"] == ""


@pytest.mark.parametrize("balance,price,expected", [("19", "19", True), ("18.99", "19", False), (None, "19", None)])
def test_budget_comparison_is_only_supplied_for_seats(balance, price, expected):
    original = state()
    original["budget"] = {"remaining_monthly_amount": balance, "unit_monthly_price": price}
    assert "budget_sufficient" not in build_response_context(original)["facts"]
    original["resource"]["access_scope"] = "SEAT"
    context = build_response_context(original)
    assert context["facts"]["budget_sufficient"] is expected
    assert "tf_member" not in context["facts"]
    assert "remaining_monthly_amount" not in json.dumps(context)


def test_old_checkpoint_ceiling_fact_is_read_without_recomputing_policy():
    original = state()
    original.pop("maximum_role")
    original["evidence"] = [{"kind": "employee_facts", "maximum_role": "Read", "budget": "private-budget"}]
    assert build_response_context(original)["facts"]["maximum_role"] == "Read"


def test_sources_include_company_rules_with_provenance_within_a_fixed_budget():
    original = state()
    policies = DocumentIndex(ROOT / "data/policy_corpus.md", "policy")
    company = DocumentIndex(ROOT / "data/company-a-access-matrix.md", "business", {3, 4, 7})
    original["answer_sources"] = policies.search("push Write TF 권한", "GITHUB", 10)
    original["evidence"] = [chunk for doc in company.documents for chunk in company.read(doc)]
    original["evidence"].append({"doc_id": "A-ACCESS-02", "chunk_id": "private-employee-list", "text": "private-directory"})
    original["answer_sources"] += policies.read("JR-OFF-01")
    context = build_response_context(original)
    sources = context["sources"]
    assert len(sources) <= 8
    assert {s["doc_id"] for s in sources} >= {"A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07"}
    assert not any(s["doc_id"] in {"JR-OFF-01", "A-ACCESS-02"} for s in sources)
    assert all(s["source"] and s["version"] and len(s["source_hash"]) == 64 for s in sources)


async def test_approval_checkpoint_keeps_prepared_context_after_reopening(tmp_path):
    path = str(tmp_path / "prepared.sqlite")
    config = {"configurable": {"thread_id": "prepared-approval"}}
    tools = FakeTools()
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = build_graph(tools, saver)
        await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
        saved = await graph.aget_state(config)
        digest = Plan.model_validate(saved.values["plan"]).digest()
        count = len(tools.calls)
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = build_graph(tools, saver)
        saved = await graph.aget_state(config)
        assert saved.next == ("approval",)
        assert saved.values["response_context"]["decision"]["status"] == "WAITING_APPROVAL"
        assert saved.values["response_context"]["facts"]["maximum_role"] == "Write"
        assert Plan.model_validate(saved.values["plan"]).digest() == digest
        assert len(tools.calls) == count and tools.writes == 0


async def test_llm_generation_and_review_receive_the_same_prepared_facts_and_sources(monkeypatch):
    original = state()
    original["answer_sources"] = [{"doc_id": "GH-OFF-02", "chunk_id": "GH-OFF-02:summary",
                                    "text": "팀의 저장소 역할을 확인합니다.", "source": "policy_corpus.md", "version": "test"}]
    context = prepare_response_node(original)["response_context"]
    original["response_context"] = context
    before = deepcopy(original)
    received = []
    class FakeModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self
        async def ainvoke(self, messages):
            payload = json.loads(messages[-1][1])
            received.append(payload if self.schema is AnswerDraft else payload["context"])
            if self.schema is AnswerReview:
                return AnswerReview(supported=True)
            return AnswerDraft(answerable=True, steps=[AnswerStep(text="팀의 저장소 역할을 확인하세요.",
                citations=[Citation(chunk_id="GH-OFF-02:summary", quote="팀의 저장소 역할을 확인합니다.")])])
    monkeypatch.setattr(answering, "model", FakeModel)
    monkeypatch.setattr(answering, "settings", replace(answering.settings, mode="llm"))
    draft, code = await answering.generate_answer(original)
    assert draft is not None and code == "RAG_GUIDANCE"
    assert received == [context, context] and original == before
