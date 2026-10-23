import test from 'node:test'
import assert from 'node:assert/strict'
import { canDecide, statusLabel, costLabel, candidateLabel } from '../src/phase2/presentation.ts'
import { Submission } from '../src/phase2/submission.ts'

test('only the current bound approver can decide; hold remains distinct from rejection', () => {
  const view = {
    status: 'WAITING_APPROVAL',
    plan_hash: 'a'.repeat(64),
    plan_version: 2,
    current_step: 2,
    approval_steps: [
      { step: 1, approver_id: 'first', status: 'APPROVED' },
      { step: 2, approver_id: 'second', status: 'WAITING' }
    ]
  }
  assert.equal(canDecide(view, 'second'), true)
  for (const actor of ['first', 'requester', undefined]) assert.equal(canDecide(view, actor), false)
  assert.equal(canDecide({ ...view, plan_hash: null }, 'second'), false)
  for (const plan_version of [undefined, null, 0, -1, 1.5])
    assert.equal(canDecide({ ...view, plan_version }, 'second'), false)
  assert.equal(canDecide({ ...view, status: 'ON_HOLD' }, 'second'), false)
  assert.equal(statusLabel({ status: 'ON_HOLD' }), '보류')
})

test('scan completion, verified access, unknown cost and unknown candidates stay distinct', () => {
  assert.equal(statusLabel({ run_id: 'run', status: 'DONE' }), '점검 완료')
  assert.equal(statusLabel({ status: 'DONE', result_type: 'GUIDANCE' }), '안내 완료')
  assert.equal(
    statusLabel({ status: 'DONE', result_type: 'ACCESS_VERIFIED', verification_ok: true }),
    '권한 반영 확인'
  )
  assert.equal(
    statusLabel({ status: 'DONE', result_type: 'ACCESS_VERIFIED', verification_ok: null }),
    '완료 상태 확인 필요'
  )
  assert.equal(costLabel({ status: 'UNKNOWN', monthly_amount: null, currency: null }), '비용 미확인')
  assert.equal(
    costLabel({ status: 'ESTIMATED', monthly_amount: '0.00', currency: 'USD' }),
    '0.00 USD / 월 (예상)'
  )
  assert.equal(candidateLabel({ candidate_status: null, review_required: true }), '추가 확인')
})

test('v2 submission reuses a persisted retry key and isolates users, operation types and accepted intents', async () => {
  const saved = new Map(),
    storage = () => ({
      getItem: (k) => saved.get(k) ?? null,
      setItem: (k, v) => saved.set(k, v),
      removeItem: (k) => saved.delete(k)
    })
  const input = { schema_version: 2, contents: 'private request' },
    keys = []
  await assert.rejects(
    new Submission(storage).submit('a', 'access', input, async (body, key) => {
      keys.push(key)
      throw new Error('response lost')
    })
  )
  assert.ok(![...saved.values()].join('').includes('private request'))
  const submitter = new Submission(storage)
  let release
  const send = (body, key) => {
    keys.push(key)
    return new Promise((resolve) => {
      release = resolve
    })
  }
  const first = submitter.submit('a', 'access', input, send)
  assert.equal(submitter.submit('a', 'access', input, send), first)
  await assert.rejects(submitter.submit('a', 'access', { ...input, contents: 'different' }, send))
  while (!release) await new Promise((resolve) => setImmediate(resolve))
  release({ problem_id: 'accepted', status: 'DONE' }) // Replay may already have progressed beyond RECEIVED.
  await first
  assert.equal(keys[0], keys[1])
  const accept = async (body, key) => {
    keys.push(key)
    return {}
  }
  await submitter.submit('a', 'access', input, accept)
  await submitter.submit('b', 'access', input, accept)
  await submitter.submit('a', 'reclaim', { scope_id: 'scope' }, accept)
  assert.equal(new Set(keys.slice(1)).size, 4)
})
