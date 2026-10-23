"""The frozen upgrade policy must remain usable by the same tenant-bound RAG reader."""
import hashlib
from pathlib import Path
import re
import pytest
from unlockops.access.selection import select_entitlement
from unlockops_rag.approval import approval_evidence
from unlockops_rag.revisions import revision_index

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('platform', ['GITHUB', 'JIRA', 'SLACK', 'NOTION'])
def test_upgrade_policy_is_hash_bound_and_covers_existing_platforms(platform):
    sql = (ROOT / 'backend/src/main/resources/db/migration/V9__unify_existing_accounts.sql').read_text()
    match = re.search(r"'([a-f0-9]{64})',\$existing_policy\$(.*?)\$existing_policy\$", sql, re.S)
    assert match
    source_hash, content = match.groups()
    assert hashlib.sha256(content.encode()).hexdigest() == source_hash
    index = revision_index('existing-company', 'existing-policy', 1, 'EXISTING-POLICY', source_hash, content, platform)
    evidence = index.read()
    assert approval_evidence(evidence, platform)
    assert any(e['article'].startswith('FLOW |') for e in evidence)
    assert any(e['article'].split(' | ')[1] == platform for e in evidence)
    assert all(e['article'].split(' | ')[1] in {'COMMON', platform} for e in evidence)


async def test_existing_notion_view_request_resolves_to_imported_viewer():
    context = {'problem': {'platform': 'NOTION', 'contents': 'Notion 개발팀 위키 Can view 권한 주세요'},
        'entitlements': [{'id': code, 'resource_id': 'wiki', 'external_id': 'dev-wiki', 'name': '개발팀 위키',
                          'code': code, 'kind': 'ROLE'} for code in ('VIEWER', 'EDITOR')]}
    assert await select_entitlement(context, {'requested_role': 'Can view'}) == ('VIEWER', False)
