"""Small regressions for the supplied corpus, tenant binding and generated revision update."""
import hashlib
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from unlockops.common.models import ToolFailure
from unlockops_rag.corpus import parse_corpus
from unlockops_rag.revisions import revision_index
from unlockops_mcp.phase2_policy import scoped_index

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'data/phase2/policies'


def test_supplied_documents_keep_ids_versions_and_platforms():
    docs = {d.doc_id: d for d in parse_corpus((DIRECTORY / 'policy_corpus.md').read_text())}
    assert len(docs) == 28
    assert {d.platform for d in docs.values()} == {'COMMON', 'GITHUB', 'JIRA', 'SLACK', 'NOTION', 'SNOWFLAKE', 'DATABRICKS', 'SALESFORCE', 'DATADOG', 'TABLEAU_CLOUD', 'FIGMA'}
    assert docs['POL-06'].platform == 'COMMON'
    assert docs['POL-06'].version == 'v1.1'
    assert docs['POL-04'].version == 'v1.0'
    assert docs['FG-OFF-01'].version == '2026-10-22'
    assert len(docs['POL-06'].chunks) == 5
    assert dict(docs['FG-OFF-01'].chunks)['원문'].find('https://www.figma.com/pricing/') >= 0


def test_mcp_uses_company_revision_and_request_platform_without_article_collisions():
    content = (DIRECTORY / 'company-a-policy-v2.md').read_text()
    digest = hashlib.sha256(content.encode()).hexdigest()
    policy = dict(company_id=str(uuid4()), policy_id=str(uuid4()), revision=2,
                  doc_id='P2-A-POLICY', source_hash=digest, content=content)
    class Repo:
        def invoke(self, name, args):
            if name == 'get_access_request_context':
                return {'problem': {'platform': 'FIGMA'}, 'policies': [policy]}
            return {'context': {'policy': policy}}
    index = scoped_index(Repo(), 'ACCESS_REQUEST', str(uuid4()), digest)
    evidence = index.read()
    articles = [e['article'] for e in evidence]
    assert len(articles) == len(set(articles))
    assert any(a.startswith('POL-14 | FIGMA |') for a in articles)
    assert any(a.startswith('POL-06 | COMMON |') for a in articles)
    assert not any(a.startswith('POL-09 |') for a in articles)
    assert all(e['doc_id'] == 'P2-A-POLICY' and e['version'] == '2' and e['text'] in content for e in evidence)
    assert any(e['article'].startswith(('POL-14 |', 'FG-OFF-01 |')) for e in index.search('Figma Full 좌석 디자인 편집', 5))
    assert any('30일' in e['text'] for e in scoped_index(Repo(), 'RECLAIM_SCAN', str(uuid4()), digest).search('TF 종료 미사용 30일 유지 승인', 5))
    with pytest.raises(ToolFailure):
        scoped_index(Repo(), 'ACCESS_REQUEST', str(uuid4()), '0' * 64)
    # A corrupt document cannot be reused from an earlier index entry.
    with pytest.raises(ToolFailure):
        revision_index(policy['company_id'], policy['policy_id'], 2, policy['doc_id'], digest, content + '변경')


def test_generated_policy_bundles_and_sql_are_reproducible():
    spec = importlib.util.spec_from_file_location('policy_import', ROOT / 'scripts/import_phase2_policy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path, content in module.outputs().items():
        assert path.read_text() == content
    a = (DIRECTORY / 'company-a-policy-v2.md').read_text()
    b = (DIRECTORY / 'company-b-policy-v2.md').read_text()
    assert '100.00 USD 이상' not in a and '100.00 USD 이상' in b
    assert '15.00 USD' in a and '월 16달러' in a
