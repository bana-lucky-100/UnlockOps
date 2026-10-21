import pytest

from unlockops.models import ToolFailure
from unlockops.tools import ScopedTools
from conftest import FakeTools, ROOT
from unlockops_rag.search import DocumentIndex
from unlockops.settings import settings


@pytest.mark.parametrize("name,args",[
    ("grant_permission",{"problem_id":"p","idempotency_key":"x"}),
    ("get_employee_profile",{"employee_id":"someone-else"}),
    ("resolve_resource",{"platform":"JIRA","hint":"PAY"}),
    ("get_current_permissions",{"employee_id":"me","resource_id":"different-resource"}),
])
async def test_tool_scope_blocks_cross_identity_platform_resource_and_writes(name,args):
    """다른 직원·플랫폼·자원 조회와 진단 중 쓰기를 원격 호출 전에 차단한다."""
    transport=FakeTools(); scoped=ScopedTools(transport,"me","GITHUB","repo")
    with pytest.raises(ToolFailure): await scoped.read(name,args)
    assert transport.calls==[]


def test_policy_articles_are_traceable_and_platform_filtered(monkeypatch):
    """정책 검색 결과의 조항·출처 해시와 플랫폼 필터를 확인한다."""
    monkeypatch.delenv("EMBEDDING_BASE_URL",raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL",raising=False)
    index=DocumentIndex(ROOT/"data/policy_corpus.md","policy")
    article=index.read("POL-03","제4조")
    assert "Admin" in article[0]["text"]
    assert len(article[0]["source_hash"])==64
    hits=index.search("GitHub Admin 자동 부여 금지","GITHUB",8)
    assert hits
    assert all(h["platform"] in {"GITHUB","COMMON"} for h in hits)


def test_company_rag_excludes_employee_and_sample_login_sections(monkeypatch):
    """직원 정보와 로그인 예시를 제외한 허용 절만 검색하는지 확인한다."""
    monkeypatch.delenv("EMBEDDING_BASE_URL",raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL",raising=False)
    index=DocumentIndex(ROOT/"data/company-a-access-matrix.md","business",{3,4,7})
    assert set(index.documents)=={"A-ACCESS-03","A-ACCESS-04","A-ACCESS-07"}
    with pytest.raises(ValueError): index.read("A-ACCESS-02")
    assert index.search("TF 개발 사원 Write")


async def test_optional_cache_is_bounded_and_not_shared_between_analyses():
    """캐시 적중도 선택 호출 한도에 포함하고 분석 간 캐시는 공유하지 않는다."""
    tools = FakeTools()
    scoped = ScopedTools(tools, "me", "GITHUB")
    args = {"employee_id": "me"}
    await scoped.read("get_employee_profile", args)
    for _ in range(settings.max_optional_tools):
        await scoped.read("get_employee_profile", args, optional=True)
    with pytest.raises(ToolFailure, match="Optional tool"):
        await scoped.read("get_employee_profile", args, optional=True)
    assert scoped.calls == 1
    assert len(tools.calls) == 1
    await ScopedTools(tools, "me", "GITHUB").read("get_employee_profile", args)
    assert len(tools.calls) == 2


async def test_large_model_tool_batch_cannot_starve_mandatory_evidence(monkeypatch):
    """모델이 많은 도구를 요청해도 필수 근거를 먼저 확보하고 호출 한도를 지킨다."""
    from dataclasses import replace
    from types import SimpleNamespace
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops.graph import build_graph
    from unlockops.planner import raw_intent
    from test_scenarios import job

    class BusyModel:
        def bind_tools(self, descriptions):
            """도구 목록을 받는 모델 인터페이스를 네트워크 없이 흉내 낸다."""
            return self

        async def ainvoke(self, messages):
            """선택 조회 한도를 넘는 정책 검색 요청을 한 번에 반환한다."""
            return SimpleNamespace(tool_calls=[{
                "id": str(i), "name": "search_policy",
                "args": {"query": f"extra query {i}", "platform": "GITHUB"},
            } for i in range(100)])

    async def parse(contents, platform):
        """모델 호출 없이 데모 규칙으로 요청 의도를 만든다."""
        return raw_intent(contents)

    monkeypatch.setattr("unlockops.graph.interpret", parse)
    monkeypatch.setattr("unlockops.planner.settings", replace(settings, mode="llm"))
    monkeypatch.setattr("unlockops.planner.model", BusyModel)
    tools = FakeTools()
    result = await build_graph(tools, InMemorySaver()).ainvoke(
        {"job": job("GITHUB", "payment-core push가 안 돼요")},
        {"configurable": {"thread_id": "busy-model"}},
    )
    assert result["result"]["status"] == "WAITING_APPROVAL"
    assert result["evidence_complete"] is True
    assert result["optional_tool_calls"] == settings.max_optional_tools
    assert result["tool_calls"] <= settings.max_tools
    collected = next(e for e in result["events"] if e["node"] == "collect_evidence")
    assert collected["investigation"] == "tool_budget_exhausted"
    names = [name for name, _ in tools.calls]
    assert names.index("get_current_permissions") < names.index("read_access_rule")
    assert names[-settings.max_optional_tools:] == ["search_policy"] * settings.max_optional_tools
    assert tools.writes == 0


async def test_mandatory_tool_failure_never_produces_approval():
    """필수 사실 조회에 실패하면 승인 계획을 만들거나 권한을 변경하지 않는다."""
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops.graph import build_graph
    from test_scenarios import job

    class MissingFacts(FakeTools):
        async def call(self, name, args):
            """현재 권한 조회에만 일시 오류를 발생시킨다."""
            if name == "get_current_permissions":
                raise ToolFailure("UPSTREAM_UNAVAILABLE", "facts unavailable", True)
            return await super().call(name, args)

    tools = MissingFacts()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "missing-facts"}}
    with pytest.raises(ToolFailure):
        await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    saved = await graph.aget_state(config)
    assert saved.values.get("plan") is None
    assert tools.writes == 0
