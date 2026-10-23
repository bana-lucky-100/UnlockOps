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

import { fromOverview, isNewInRun, isAlreadyNotified, needsReviewRow, pickScope } from '../src/lib/revocation.ts'

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

import { summaryOf, judgmentOf } from '../src/lib/requestView.ts'
test('이미 보유는 안내 완료와 구분해 "이미 보유"로 보이고 해요체로 설명한다', () => {
  const p = fromV2(report({ status: 'DONE', reason_code: 'ALREADY_HAS_ACCESS', result_type: 'GUIDANCE', current_step: null, message: '조회 결과 필요한 권한을 이미 보유하고 있습니다.' }))
  assert.equal(statusOf(p).label, '이미 보유')
  assert.match(summaryOf(p), /이미 보유하고 있어요/)
  assert.match(judgmentOf(p, true), /있어요/)
})

import { costImpactOf } from '../src/lib/costImpact.ts'
import { checksOf } from '../src/lib/evidenceView.ts'
test('리뷰 반영: 알림 시각 없는 후보는 이미 알림이 아니고, 빠진 금액은 $NaN이 되지 않고, TF 사실이 없으면 미충족으로 단정하지 않는다', () => {
  const run = { id: 'r', task_type: 'RECLAIM_SCAN', trigger: 'UNKNOWN', status: 'DONE', reason_code: 'SCAN_COMPLETED', started_at: '2026-10-23T00:00:00Z', finished_at: null }
  const c = { candidate_status: 'PENDING_REVIEW', notified_at: null }
  assert.equal(isAlreadyNotified(c, run), false)
  assert.equal(isNewInRun(c, run), false)
  assert.equal(costImpactOf({ status: 'WAITING_APPROVAL', cost_impact: { kind: 'NEW_COST' } }), null)
  const ok = costImpactOf({ status: 'WAITING_APPROVAL', cost_impact: { kind: 'NEW_COST', monthly_cost: 19 } })
  assert.equal(ok.impact.budget_before, null)
  const p = { requested_role: 'Write', reason_code: 'ELIGIBLE', evidence: [{ kind: 'employee_facts', maximum_role: 'Write' }, { doc_id: 'POL-02', text: '제1조 TF' }] }
  assert.ok(!checksOf(p, [{ id: 'POL-02' }]).some(x => x.text.includes('TF 명단')))
})

test('수동 회수 점검은 평가용 범위가 아니라 기본 유료 좌석 범위를 고른다', () => {
  const scopes = [
    { id: 'm', scope_key: 'phase2:A:MISSING_USAGE', enabled: false },
    { id: 'r2', scope_key: 'phase2:A:R-02', enabled: false },
    { id: 'main', scope_key: 'phase2:A:paid-seats', enabled: false },
  ]
  assert.equal(pickScope(scopes).id, 'main')
  assert.equal(pickScope([...scopes, { id: 'on', scope_key: 'phase2:A:X-11', enabled: true }]).id, 'on')
  assert.equal(pickScope([{ id: 'x', scope_key: 'other', enabled: false }]).id, 'x')
  assert.equal(pickScope([]), undefined)
})

test('회수 근거와 비용 근거는 규정 ID와 조항만 짧게 보여 준다', async () => {
  const { shortArticle, policyRefs } = await import('../src/lib/policyRef.ts')
  assert.equal(shortArticle('POL-06 | COMMON | v1.1 | 제5조(회수 점검)'), 'POL-06 제5조(회수 점검)')
  assert.equal(shortArticle('POL-06 제2조'), 'POL-06 제2조')
  assert.equal(policyRefs([
    { article: 'BASELINE | COMMON | 3 | 회수 점검의 구현 기준' },
    { article: 'POL-06 | COMMON | v1.1 | 제5조(회수 점검)' },
    { article: 'GH-OFF-03 | GITHUB | 2026-10-22 | 핵심 요약' },
    { article: 'POL-06 | COMMON | v1.1 | 제5조(회수 점검)' },
  ]), 'POL-06 제5조(회수 점검)')
})

test('개요에 이름 · 사용일이 없으면 지어내지 않고 정보 없음으로 둔다', () => {
  const base = { candidate_status: 'PENDING_REVIEW', explanation: 'x', policy_evidence: [], cost_impact: { status: 'ESTIMATED', monthly_amount: '19.00', currency: 'USD' } }
  const r = fromOverview({ last_run: null, active_run: null, summary: null, targets: [{ ...base, assignment_id: 'a', platform: 'GITHUB' }] })
  assert.equal(r.candidates[0].user_name, '')
  assert.equal(r.candidates[0].usage_known, false)
  const r2 = fromOverview({ last_run: null, active_run: null, summary: null, targets: [{ ...base, assignment_id: 'b', platform: 'GITHUB', employee_name: '김지성', resource_name: 'Copilot', last_used_at: '2026-09-05T09:00:00+09:00' }] })
  assert.equal(r2.candidates[0].user_name, '김지성')
  assert.equal(r2.candidates[0].resource, 'Copilot')
  assert.equal(r2.candidates[0].usage_known, true)
})

test('회수 버튼은 서버가 can_revoke를 준 후보에만 열린다', () => {
  const base = { candidate_status: 'PENDING_REVIEW', explanation: 'x', policy_evidence: [], cost_impact: { status: 'ESTIMATED', monthly_amount: '19.00', currency: 'USD' }, platform: 'GITHUB' }
  const r = fromOverview({ last_run: null, active_run: null, summary: null, targets: [{ ...base, assignment_id: 'a' }, { ...base, assignment_id: 'b', can_revoke: true }, { ...base, assignment_id: 'c', candidate_status: 'RECLAIMED', reclaimed_at: '2026-10-23T15:20:00+09:00' }] })
  assert.deepEqual(r.candidates.map(c => c.can_revoke), [false, true, false])
  assert.equal(r.candidates[2].candidate_status, 'RECLAIMED')
  assert.equal(r.candidates[2].reclaimed_at, '2026-10-23T15:20:00+09:00')
})

test('헤더 프로필은 로그인 카드와 같은 이니셜 · 색을 쓴다', async () => {
  const { personaAvatar } = await import('../src/lib/persona.ts')
  assert.equal(personaAvatar({ login_id: 'p2_a_head', name: '김동빈' }).initial, '동')
  assert.equal(personaAvatar({ login_id: 'p2_a_operator', name: '신형철' }).fg, '#2B3480')
  assert.equal(personaAvatar({ login_id: 'p2_b_requester', name: '박요청(B)' }).initial, '요')
  assert.equal(personaAvatar({ name: '😀' }).initial, '😀')
})
