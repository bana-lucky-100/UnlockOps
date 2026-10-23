import test from 'node:test'
import assert from 'node:assert/strict'
import { fromV2, isMyStep } from '../src/lib/v2view.ts'
import { isGuidanceComplete, statusOf, doneKind } from '../src/lib/status.ts'

const ID = '11111111-1111-4111-8111-111111111111'
const HEAD = '22222222-2222-4222-8222-222222222222'
const OPS = '33333333-3333-4333-8333-333333333333'
const HASH = 'a'.repeat(64)

function report(workflow, extra = {}) {
  return {
    workflow: {
      schema_version: 2, task_type: 'ACCESS_REQUEST', problem_id: ID, status: 'WAITING_APPROVAL', message: '1단계 승인을 기다리고 있어요',
      reason_code: 'ELIGIBLE', current_step: 1, total_steps: 2, plan_hash: HASH, plan_version: 1,
      approval_steps: [
        { step: 1, approver_id: HEAD, status: 'WAITING', reason: null, acted_at: null },
        { step: 2, approver_id: OPS, status: 'PENDING', reason: null, acted_at: null },
      ],
      ...workflow,
    },
    contents: '분석용 Snowflake 권한 필요', platform: 'SNOWFLAKE', requester_id: 'r1', requester_name: '김개발', created_at: '2026-10-23T01:00:00Z',
    analysis_summary: '규정과 예산 조건을 모두 충족해요', resource_name: 'ANALYTICS_WH', entitlement_code: 'USAGE',
    policy_evidence: [{ doc_id: 'POL-06', article: '제2조', version: 'v1.1', source_hash: 'x', text: '제2조 예상 비용은 잔여 예산 이하' }],
    approvers: [{ id: HEAD, name: '윤부장' }, { id: OPS, name: '송운영' }],
    plan: { schema_version: 2, problem_id: ID, resource_id: 'res-1', monthly_amount: '120.00', currency: 'USD', cost_basis: 'USAGE_ESTIMATE' },
    history: [{ id: 1, kind: 'V2_REQUESTED', created_at: '2026-10-23T01:00:00Z' }],
    ...extra,
  }
}

test('v2 보고서를 화면 Problem으로 옮긴다: 단계 · 근거 · 대상 · 비용', () => {
  const p = fromV2(report({}))
  assert.equal(p.id, ID)
  assert.equal(p.status, 'WAITING_APPROVAL')
  assert.equal(p.total_steps, 2)
  assert.equal(p.plan?.resource_key, 'ANALYTICS_WH')
  assert.equal(p.requested_role, 'USAGE')
  assert.equal(p.evidence?.[0].doc_id, 'POL-06')
  assert.equal(p.cost_impact?.kind, 'NEW_COST')
  assert.equal(p.cost_impact?.monthly_cost, 120)
  assert.equal(p.cost_impact?.budget_before, null)
  assert.equal(statusOf(p).label, '1/2단계 승인 대기')
})

test('목록 요약에는 상세 값이 없어도 깨지지 않는다', () => {
  const { workflow, contents, platform, requester_id, requester_name, created_at } = report({})
  const p = fromV2({ workflow, contents, platform, requester_id, requester_name, created_at })
  assert.equal(p.plan, null)
  assert.deepEqual(p.evidence, [])
  assert.equal(p.cost_impact, null)
})

test('현재 단계의 지정 승인자만 결정할 수 있다', () => {
  const p = fromV2(report({}))
  assert.equal(isMyStep(p, HEAD), true)
  assert.equal(isMyStep(p, OPS), false)
  const done = fromV2(report({ status: 'DONE', current_step: null }))
  assert.equal(isMyStep(done, HEAD), false)
})

test('안내 완료는 result_type으로만 판단하고, 완료 문구도 result_type을 따른다', () => {
  const g = fromV2(report({ status: 'DONE', reason_code: null, result_type: 'GUIDANCE', current_step: null }))
  assert.equal(isGuidanceComplete(g), true)
  assert.equal(doneKind(g), 'RAG_GUIDANCE')
  const v = fromV2(report({ status: 'DONE', reason_code: null, result_type: 'ACCESS_VERIFIED', current_step: null }))
  assert.equal(isGuidanceComplete(v), false)
  assert.equal(doneKind(v), 'VERIFIED')
})

test('마지막 결정자 이름과 사유를 단계 기록에서 가져온다', () => {
  const p = fromV2(report({
    status: 'REJECTED', reason_code: 'HUMAN_REJECTED', current_step: null,
    approval_steps: [
      { step: 1, approver_id: HEAD, status: 'APPROVED', reason: null, acted_at: '2026-10-23T02:00:00Z' },
      { step: 2, approver_id: OPS, status: 'REJECTED', reason: '예산 재확인 필요', acted_at: '2026-10-23T03:00:00Z' },
    ],
  }))
  assert.equal(p.decided_by, '송운영')
  assert.equal(p.decision_reason, '예산 재확인 필요')
  assert.equal(p.decided_at, '2026-10-23T03:00:00Z')
})

import { fromOverview, isNewInRun, isAlreadyNotified, needsReviewRow } from '../src/lib/revocation.ts'

test('v2 회수 개요: 이번 점검에 알린 후보는 신규, 이미 알린 후보는 다시 알리지 않고, 비용 미확인은 0원으로 세지 않는다', () => {
  const asOf = '2026-10-23T00:00:00Z'
  const r = fromOverview({
    active_run: null,
    last_run: { run_id: 'r1', status: 'DONE', reason_code: 'SCAN_COMPLETED', as_of: asOf, scan_complete: true,
      needs_review: [{ assignment_id: 'a9', employee_name: '이운영', resource_name: 'Notion 좌석', missing: ['USAGE_OBSERVATION'] }] },
    summary: { new_candidate_count: 1, needs_review_count: 1, monthly_saving_by_currency: { USD: '19.00' } },
    targets: [
      { assignment_id: 'a1', target_id: 't1', platform: 'GITHUB', candidate_status: 'PENDING_REVIEW', notified_at: '2026-10-23T00:01:00Z', explanation: '47일 미사용', cost_impact: { status: 'ESTIMATED', monthly_amount: '19.00', currency: 'USD' } },
      { assignment_id: 'a2', target_id: 't2', platform: 'FIGMA', candidate_status: 'PENDING_REVIEW', skip_reason_code: 'ALREADY_NOTIFIED', notified_at: '2026-10-20T00:00:00Z', explanation: '41일 미사용', cost_impact: { status: 'UNKNOWN' } },
    ],
  }, p => p)
  const [fresh, old] = r.candidates
  assert.equal(isNewInRun(fresh, r.run), true)
  assert.equal(isAlreadyNotified(old, r.run), true)
  assert.equal(old.cost_known, false)
  assert.equal(r.summary.monthly_saving, 19)
  assert.deepEqual(needsReviewRow(r.needs_review[0]).missing, ['사용 기록'])
})

import { budgetFromMessage } from '../src/lib/v2view.ts'
test('[임시] 판정 메시지에서 부서 잔여 예산 전후 값을 읽고, 비용 근거 조항을 붙인다', () => {
  assert.deepEqual(budgetFromMessage('정책·직무·예산을 확인했습니다. 예상 예산 영향은 500.00 → 380.00 USD입니다. 순서대로 승인을 기다립니다.', 'USD'), { before: 500, after: 380 })
  assert.equal(budgetFromMessage('승인을 기다리고 있어요', 'USD'), null)
  assert.equal(budgetFromMessage('예상 예산 영향은 500.00 → 380.00 KRW입니다', 'USD'), null)
  const p = fromV2(report({ message: '예상 예산 영향은 500.00 → 380.00 USD입니다.' }))
  assert.equal(p.cost_impact?.budget_before, 500)
  assert.equal(p.cost_impact?.budget_after, 380)
  assert.match(p.cost_impact?.basis ?? '', /분석용 웨어하우스 월 사용/)
  assert.match(p.cost_impact?.rule ?? '', /^판정에 쓴 규정 POL-06/)
})

import { decisionSummaryOf, objectJosa } from '../src/lib/decisionSummary.ts'
test('한 장 요약: 결론 · 숫자 · 왜 괜찮은지 · 승인 순서를 서버 값으로만 만든다', () => {
  assert.equal(objectJosa('Snowflake 웨어하우스 이용 권한'), '을')
  assert.equal(objectJosa('Slack 채널 참여'), '를')
  const p = fromV2(report({ message: '예상 예산 영향은 500.00 → 380.00 USD입니다.' }))
  const s = decisionSummaryOf(p, 'Snowflake 웨어하우스 이용 권한', p.cost_impact)
  assert.equal(s.headline, 'Snowflake 웨어하우스 이용 권한을 승인해도 돼요')
  assert.deepEqual(s.numbers.map(n => n.big), ['월 $120', '$500 → $380', '24%'])
  assert.ok(s.checks.some(c => c.text.includes('$380 남아요')))
  assert.deepEqual(s.steps.map(x => `${x.who}:${x.state}`), ['윤부장:on', '송운영:wait', '자동:wait'])
  assert.equal(decisionSummaryOf(fromV2(report({ status: 'DONE', current_step: null })), 'x', null), null)
})
