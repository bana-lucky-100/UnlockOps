"""Document guidance remains in the current workflow and cannot execute a grant."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from unlockops.access import answering, graph
from unlockops.access.answering import AnswerDraft, AnswerReview, AnswerStep, Citation
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings
from unlockops_rag.revisions import revision_index
from unlockops_worker.runtime import run_job
from test_workflows import AccessTools, access_job, context, policy

ROOT = Path(__file__).resolve().parents[2]


def guidance_tools(job, question, *, existing=False, corrupt=False):
    ctx = context(job)
    ctx['problem'].update(platform='GITHUB', contents=question, requested_entitlement_id=None, resource_id=None)
    ctx['entitlements'][0].update(platform='GITHUB', name='payment-core', code='WRITE')
    content = (ROOT/'data/phase2/policies/company-a-policy-v3.md').read_text()
    p = {**policy(), 'revision': 3, 'content': content, 'source_hash': hashlib.sha256(content.encode()).hexdigest()}
    ctx['policies'] = [p]
    index = revision_index(p['company_id'], p['policy_id'], 3, p['doc_id'], p['source_hash'], content, 'GITHUB')
    class Tools(AccessTools):
        async def call(self, name, args):
            self.calls.append(name)
            if name == 'get_access_request_context': return deepcopy(ctx)
            if name in {'read_workflow_policy', 'search_workflow_policy'}:
                evidence = index.read() if name == 'read_workflow_policy' else index.search(args['query'], args['limit'])
                if corrupt and evidence: evidence[0]['text'] += ' invented source'
                return {'source_hash': p['source_hash'], 'evidence': evidence, 'retrieval_mode': 'exact'}
            if name == 'assess_access_request' and existing:
                return {'status': 'DONE', 'reason': 'ALREADY_HAS_ACCESS', 'message': '요청한 권한을 이미 보유합니다.', 'evidence': index.read()}
            raise AssertionError(name)
    return Tools(job)


@pytest.mark.parametrize('question', ['GitHub Read와 Write 역할 차이를 설명해주세요', 'GitHub 권한 신청 절차는 어떻게 되나요?'])
async def test_guide_uses_current_company_policy_without_assessment_or_grant(question):
    job = access_job(); tools = guidance_tools(job, question)
    event = await run_job(job, InMemorySaver(), tools)
    assert (event['result']['status'], event['result']['result_type'], event['result']['reason_code']) == ('DONE', 'GUIDANCE', 'RAG_GUIDANCE')
    assert event['result']['plan_hash'] is None and event['result']['verification_ok'] is None
    assert event['policy_evidence'] and '근거:' in event['result']['message']
    assert all(e['version'] == '3' for e in event['policy_evidence'])
    assert 'assess_access_request' not in tools.calls and 'execute_access_plan' not in tools.calls


async def test_existing_permission_error_uses_guidance_without_new_approval():
    job = access_job(); tools = guidance_tools(job, 'GitHub payment-core Write 권한은 있는데 push가 안 돼요', existing=True)
    event = await run_job(job, InMemorySaver(), tools)
    assert event['result']['reason_code'] == 'RAG_GUIDANCE'
    assert event['result']['status'] == 'DONE' and event['result']['verification_ok'] is None
    assert tools.calls.count('assess_access_request') == 1
    assert 'execute_access_plan' not in tools.calls


@pytest.mark.parametrize('question,corrupt', [('GitHub에서 SSH remote 설정 방법을 알려주세요', False), ('GitHub 테마 설정 방법 알려주세요', False), ('GitHub 권한 신청 절차 알려주세요', True)])
async def test_uncovered_or_corrupt_sources_require_manual_review(question, corrupt):
    job = access_job(); tools = guidance_tools(job, question, corrupt=corrupt)
    event = await run_job(job, InMemorySaver(), tools)
    assert (event['result']['status'], event['result']['reason_code']) == ('MANUAL_REVIEW', 'MISSING_SOURCE_EVIDENCE')
    assert 'execute_access_plan' not in tools.calls


def answer_state():
    return {'response_context': {'question': 'GitHub push 권한 점검 방법', 'platform': 'GITHUB', 'resource': None,
        'sources': [{'chunk_id': 'checked-source', 'text': '팀의 저장소 역할을 확인합니다.'}],
        'decision': {'handling': 'ANSWER'}, 'facts': {}, 'writing_guide': []}}


@pytest.mark.parametrize('fault,expected', [(None, 'RAG_GUIDANCE'), ('id', 'INVALID_ANSWER_EVIDENCE'), ('quote', 'INVALID_ANSWER_EVIDENCE'), ('claim', 'ANSWER_NOT_GROUNDED'), ('no_answer', 'ANSWER_SOURCE_UNAVAILABLE')])
async def test_llm_citations_and_claims_are_checked(monkeypatch, fault, expected):
    class Model:
        def with_structured_output(self, schema): self.schema = schema; return self
        async def ainvoke(self, messages):
            if self.schema is AnswerReview: return AnswerReview(supported=fault != 'claim')
            return AnswerDraft(answerable=fault != 'no_answer', steps=[AnswerStep(text='담당자와 역할을 확인하세요.', citations=[Citation(
                chunk_id='invented' if fault == 'id' else 'checked-source', quote='없는 명령어' if fault == 'quote' else '저장소 역할을 확인합니다.')])])
    monkeypatch.setattr(answering, 'settings', replace(settings, mode='llm'))
    monkeypatch.setattr(answering, 'model', Model)
    draft, code = await answering.generate_answer(answer_state())
    assert code == expected and (draft is not None) == (fault is None)


async def test_guidance_model_outage_stays_in_review(monkeypatch):
    async def unavailable(state): raise ToolFailure('MODEL_UNAVAILABLE', 'private provider response')
    monkeypatch.setattr(graph, 'generate_answer', unavailable)
    job = access_job(); tools = guidance_tools(job, 'GitHub 권한 신청 절차 알려주세요')
    event = await run_job(job, InMemorySaver(), tools)
    assert (event['result']['status'], event['result']['reason_code']) == ('MANUAL_REVIEW', 'MODEL_UNAVAILABLE')
    assert 'private' not in str(event) and 'execute_access_plan' not in tools.calls
