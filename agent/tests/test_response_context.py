"""Only scoped, observed facts and policy excerpts enter guidance prompts."""
from unlockops.access.response_context import build_response_context, select_sources


def state():
    return {'context': {'problem': {'platform': 'GITHUB', 'contents': 'GitHub 권한 공유 방법'}, 'entitlements': [],
                        'requester': {'name': 'private-name', 'id': 'private-id'}},
            'assessment': {'reason': 'RAG_GUIDANCE', 'message': '안내'}, 'intent': {'request_type': 'GUIDE'},
            'guidance_evidence': [{'doc_id': 'bound-policy', 'article': 'GH-OFF-01 | GITHUB | v1 | 요약', 'text': 'GitHub 역할', 'source_hash': 'a'*64, 'version': '3'},
                                  {'doc_id': 'bound-policy', 'article': 'JR-OFF-01 | JIRA | v1 | 요약', 'text': 'Other platform', 'source_hash': 'a'*64, 'version': '3'}]}


def test_cross_platform_sources_and_employee_identity_are_excluded():
    value = state(); context = build_response_context(value)
    assert len(context['sources']) == 1 and context['sources'][0]['text'] == 'GitHub 역할'
    assert 'private' not in str(context)
    assert context['facts']['current_permissions_checked'] is False
    assert context['facts']['current_role'] is None
    assert select_sources(value)[0]['chunk_id'] == select_sources(value)[0]['chunk_id']


def test_inflight_current_checkpoint_keeps_its_checked_sources():
    value = state()
    value['evidence'] = value.pop('guidance_evidence')
    assert build_response_context(value)['sources'][0]['text'] == 'GitHub 역할'
