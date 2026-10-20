import pytest

from unlockops.models import ToolFailure
from unlockops.tools import ScopedTools
from conftest import FakeTools, ROOT
from unlockops_rag.search import DocumentIndex


@pytest.mark.parametrize("name,args",[
    ("grant_permission",{"problem_id":"p","idempotency_key":"x"}),
    ("get_employee_profile",{"employee_id":"someone-else"}),
    ("resolve_resource",{"platform":"JIRA","hint":"PAY"}),
    ("get_current_permissions",{"employee_id":"me","resource_id":"different-resource"}),
])
async def test_tool_scope_blocks_cross_identity_platform_resource_and_writes(name,args):
    transport=FakeTools(); scoped=ScopedTools(transport,"me","GITHUB","repo")
    with pytest.raises(ToolFailure): await scoped.read(name,args)
    assert transport.calls==[]


def test_policy_articles_are_traceable_and_platform_filtered(monkeypatch):
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
    monkeypatch.delenv("EMBEDDING_BASE_URL",raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL",raising=False)
    index=DocumentIndex(ROOT/"data/company-a-access-matrix.md","business",{3,4,7})
    assert set(index.documents)=={"A-ACCESS-03","A-ACCESS-04","A-ACCESS-07"}
    with pytest.raises(ValueError): index.read("A-ACCESS-02")
    assert index.search("TF 개발 사원 Write")
