"""규정 조회·판정 오류가 승인이나 작업 오류 대신 수동 검토로 종료되는지 확인한다."""

from dataclasses import replace
import shutil

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeTools, ROOT
from test_permission_proposal import FakeModel, proposal
from test_scenarios import job
from unlockops.access import graph as graph_module, permission_proposal, rules
from unlockops.common.models import ToolFailure
from unlockops_rag.search import DocumentIndex


@pytest.mark.parametrize("mode", ["demo", "llm"])
@pytest.mark.parametrize("stage", ["gather", "judge"])
@pytest.mark.parametrize("failure,code", [
    ("missing", "POLICY_SOURCE_UNAVAILABLE"),
    ("invalid_table", "INVALID_ACCESS_MATRIX"),
])
async def test_policy_failure_finishes_with_manual_review(tmp_path, monkeypatch, mode, stage, failure, code):
    """MCP 조회와 로컬 권한 판정 어느 단계에서든 원문 오류는 승인 없이 종료한다."""
    for filename in ("company-a-access-matrix.md", "policy_corpus.md"):
        shutil.copyfile(ROOT / "data" / filename, tmp_path / filename)
    matrix = tmp_path / "company-a-access-matrix.md"
    if failure == "missing":
        matrix.unlink()
    else:
        row = "| GitHub | TF 전용 저장소 (TF 구성원만) | Write | Write | Read |"
        text = matrix.read_text(encoding="utf-8")
        assert row in text
        matrix.write_text(text.replace(row, ""), encoding="utf-8")
    monkeypatch.setattr(rules, "settings", replace(rules.settings, data_dir=tmp_path))
    monkeypatch.setattr(graph_module, "settings", replace(graph_module.settings, mode=mode))
    model = FakeModel(proposal())
    monkeypatch.setattr(permission_proposal, "model", lambda: model)

    class PolicyTools(FakeTools):
        async def call(self, name, args):
            if name == "search_access_rules" and stage == "gather":
                # MCP의 상한 조회에서 실제 권한표 파서를 실행한다.
                return {"hits": [], "maximum_role": rules.ceiling(self.profile, self.resources[0])}
            if name == "read_access_rule" and matrix.exists():
                # 손상된 표라도 청크 해시는 현재 원문과 같게 해 판정 오류까지 도달한다.
                return {"chunks": DocumentIndex(matrix, "business", {3, 4, 7}).read(args["doc_id"])}
            return await super().call(name, args)

    tools = PolicyTools()
    graph = graph_module.build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "policy-failure"}}
    result = await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    assert (result["result"]["status"], result["result"]["reasonCode"]) == ("MANUAL_REVIEW", code)
    assert result["plan"] is None
    assert tools.writes == 0
    assert not (await graph.aget_state(config)).next
    assert not any(name in {"grant_permission", "verify_permission"} for name, _ in tools.calls)
    if mode == "llm" and stage == "judge" and failure == "invalid_table":
        assert model.messages  # LLM 제안 뒤의 실행 조건 검사에서 발생한 오류도 변환한다.
    else:
        assert model.messages == []


async def test_unrelated_judgment_errors_are_not_hidden_as_policy_errors(monkeypatch):
    """규정 오류로 분류하지 않은 사실 검증 실패는 기존 오류 경로를 유지한다."""
    async def invalid_facts(**kwargs):
        raise ToolFailure("INVALID_POLICY_FACTS", "invalid budget")

    monkeypatch.setattr(graph_module, "assess_permission", invalid_facts)
    graph = graph_module.build_graph(FakeTools(), InMemorySaver())
    with pytest.raises(ToolFailure) as caught:
        await graph.ainvoke(
            {"job": job("GITHUB", "payment-core push가 안 돼요")},
            {"configurable": {"thread_id": "invalid-facts"}},
        )
    assert caught.value.code == "INVALID_POLICY_FACTS"


@pytest.mark.parametrize("tool,doc_id", [("read_policy", "POL-03"), ("read_access_rule", "A-ACCESS-03")])
async def test_missing_required_document_is_manual_review(tool, doc_id):
    """MCP가 필수 문서 누락을 NOT_FOUND로 반환해도 작업 오류 대신 수동 검토한다."""
    class MissingDocument(FakeTools):
        async def call(self, name, args):
            if name == tool and args.get("doc_id") == doc_id:
                raise ToolFailure("NOT_FOUND", "document not found")
            return await super().call(name, args)

    tools = MissingDocument()
    graph = graph_module.build_graph(tools, InMemorySaver())
    result = await graph.ainvoke(
        {"job": job("GITHUB", "payment-core push가 안 돼요")},
        {"configurable": {"thread_id": "missing-required-document"}},
    )
    assert (result["result"]["status"], result["result"]["reasonCode"]) == (
        "MANUAL_REVIEW", "POLICY_SOURCE_UNAVAILABLE",
    )
    assert result["plan"] is None
    assert tools.writes == 0
