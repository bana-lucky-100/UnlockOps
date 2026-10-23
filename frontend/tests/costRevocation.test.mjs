import test from 'node:test'
import assert from 'node:assert/strict'
import { costImpactOf, isInsufficient, SAAS_MONTHLY_COST, usd } from '../src/lib/costImpact.ts'
import { daysSince } from '../src/lib/revocation.ts'

test('server cost_impact is used as is; without it and without mock mode the card stays hidden', () => {
  const impact = { kind: 'NEW_COST', monthly_cost: 120, budget_before: 500, budget_after: 380, basis: 'Snowflake' }
  assert.deepEqual(costImpactOf({ status: 'WAITING_APPROVAL', cost_impact: impact }), { impact, mock: false })
  assert.equal(costImpactOf({ status: 'WAITING_APPROVAL' }), null)
})

test('budget shortfall matches the hold rule and amounts render as dollars', () => {
  assert.equal(isInsufficient({ kind: 'NEW_COST', monthly_cost: 120, budget_before: 10, budget_after: -110 }), true)
  assert.equal(isInsufficient({ kind: 'NEW_COST', monthly_cost: 120, budget_before: 500, budget_after: 380 }), false)
  assert.equal(isInsufficient({ kind: 'NO_COST', monthly_cost: 0, budget_before: 10, budget_after: 10 }), false)
  assert.equal(usd(19), '$19')
  assert.equal(usd(-110), '−$110')
  assert.equal(Object.keys(SAAS_MONTHLY_COST).length, 10)
})

test('days since last use', () => {
  assert.equal(daysSince(null), null)
  assert.equal(daysSince(new Date(Date.now() - 47 * 86_400_000).toISOString()), 47)
})

test('budget shortfall shows as hold (finished), whether the server says REJECTED or MANUAL_REVIEW', async () => {
  const { statusOf, groupOf } = await import('../src/lib/status.ts')
  for (const status of ['REJECTED', 'MANUAL_REVIEW']) {
    const p = { status, reason_code: 'BUDGET_INSUFFICIENT', decided_at: null }
    assert.equal(statusOf(p).label, '보류')
    assert.equal(groupOf(p), 'finished')
  }
  assert.equal(statusOf({ status: 'REJECTED', reason_code: 'NOT_TF_MEMBER' }).label, '거절')
})
