import test from 'node:test'
import assert from 'node:assert/strict'
import { groupOf, isGuidanceComplete, needsRefresh, statusOf } from '../src/lib/status.ts'
import {
  aiMessageOf, approverEventsOf, approverNoticeOf, approverSummaryOf,
  noticeOf, proposalOf, requesterEventsOf, stagesOf, summaryOf,
} from '../src/lib/requestView.ts'

// 서버가 완료 상태와 완료 대상을 명시한다. 안내는 권한 반영을 뜻하지 않는다.
const guidance = {
  status: 'DONE', result_type: 'GUIDANCE', reason_code: 'RAG_GUIDANCE',
  diagnosis: '조회 결과 필요한 권한을 이미 보유하고 있습니다.',
  proposal: '조회한 현재 권한은 Write입니다.\n\n1. push는 Write 이상이 필요합니다.\n근거: GH-OFF-01:summary',
  resource_id: null, requested_role: null, verification_ok: null, decided_at: null,
  events: [
    { kind: 'PROGRESS', payload: { message: '요청을 분석하고 있습니다.' }, created_at: '2026-10-21T05:23:16Z' },
    { kind: 'ANALYZED', payload: { message: '안내가 완료됐어요' }, created_at: '2026-10-21T05:23:17Z' },
  ],
}

test('successful API guidance is finished, stops polling, and displays the actual response', () => {
  assert.equal(isGuidanceComplete(guidance), true)
  assert.deepEqual(statusOf(guidance), { label: '안내 완료', tone: 'ok', terminal: true })
  assert.equal(groupOf(guidance), 'finished')
  assert.equal(needsRefresh(guidance), false)
  assert.equal(aiMessageOf(guidance), guidance.diagnosis)
  assert.equal(proposalOf(guidance, 'GitHub'), guidance.proposal)
  assert.match(summaryOf(guidance), /안내가 완료/)
  assert.equal(approverSummaryOf(guidance), summaryOf(guidance))
  assert.equal(noticeOf(guidance), null)
  assert.equal(approverNoticeOf(guidance), null)
  const steps = stagesOf(guidance)
  assert.equal(steps.at(-1).label, '안내 제공')
  assert.ok(steps.every(s => s.kind === 'done'))
  assert.ok(steps.every(s => !['승인', '권한 부여', '반영 확인'].includes(s.label)))
})

test('requester and approver timelines describe guidance completion without rewriting earlier attempts', () => {
  const requester = requesterEventsOf(guidance)
  assert.equal(requester[0].text, guidance.events[0].payload.message)
  assert.equal(requester.at(-1).text, '안내가 완료됐어요')
  const rawResult = { status: 'DONE', result_type: 'GUIDANCE', reasonCode: 'RAG_GUIDANCE' }
  const raw = {
    ...guidance,
    events: [
      { kind: 'ANALYZED', payload: { result: { status: 'MANUAL_REVIEW', reasonCode: 'RESOURCE_NOT_UNIQUE' } } },
      { kind: 'ANALYZED', payload: { result: rawResult }, created_at: guidance.events[1].created_at },
    ],
  }
  const approver = approverEventsOf(raw)
  assert.match(approver[0].text, /검토/)
  assert.equal(approver.at(-1).text, '안내가 완료됐어요')
  assert.equal(rawResult.status, 'DONE')
})

test('manual review remains pending even when its reason and text look like guidance', () => {
  const problem = { ...guidance, status: 'MANUAL_REVIEW', result_type: null }
  assert.equal(isGuidanceComplete(problem), false)
  assert.equal(statusOf(problem).label, '담당자 검토')
  assert.equal(groupOf(problem), 'waiting')
  assert.equal(needsRefresh(problem), true)
  assert.equal(aiMessageOf(problem), null)
  assert.equal(proposalOf(problem, 'GitHub'), null)
  assert.ok(noticeOf(problem))
  assert.ok(approverNoticeOf(problem))
})

test('completion meaning is independent of reason codes and display text', () => {
  assert.equal(isGuidanceComplete({ ...guidance, reason_code: 'NEW_GUIDANCE_REASON' }), true)
  assert.equal(isGuidanceComplete({ ...guidance, result_type: 'ACCESS_VERIFIED' }), false)
  assert.equal(isGuidanceComplete({ ...guidance, result_type: null }), false)
})

test('guidance content cannot override pending, rejected, or failed workflow states', () => {
  for (const status of ['RECEIVED', 'DIAGNOSING', 'WAITING_APPROVAL', 'EXECUTING', 'REJECTED', 'FAILED']) {
    assert.equal(isGuidanceComplete({ ...guidance, status }), false)
  }
  const waiting = { status: 'WAITING_APPROVAL', requested_role: 'Write' }
  assert.equal(groupOf(waiting), 'waiting')
  assert.equal(needsRefresh(waiting), true)
  assert.equal(proposalOf(waiting, 'GitHub'), 'GitHub Write 권한을 부여하는 판단안이에요.')
  const granted = { status: 'DONE', requested_role: 'Write', verification_ok: true, decided_at: '2026-10-21T05:23:17Z' }
  // 규격 6: 완료는 사유별로 나눈다. 사유 코드가 없던 기존 완료는 승인 결정이 있으면 부여 완료.
  assert.equal(statusOf(granted).label, '부여 완료')
  assert.equal(groupOf(granted), 'finished')
  assert.equal(needsRefresh(granted), false)
  assert.match(summaryOf(granted), /권한 부여 완료/)
  assert.equal(stagesOf(granted).at(-1).label, '반영 확인')
})

test('rule rejections and manual reviews tell the requester why and what to do next, without policy ids', () => {
  const budget = noticeOf({ status: 'REJECTED', reason_code: 'BUDGET_INSUFFICIENT', decided_at: null })
  assert.equal(budget.title, '부서 예산이 부족해 보류됐어요')
  assert.match(budget.why, /월 비용/)
  assert.match(budget.next, /예산 증액/)
  const held = noticeOf({ status: 'MANUAL_REVIEW', reason_code: 'BUDGET_INSUFFICIENT', decided_at: null })
  assert.equal(held.title, budget.title)
  const tf = noticeOf({ status: 'REJECTED', reason_code: 'NOT_TF_MEMBER', decided_at: null })
  assert.match(tf.next, /TF 리더/)
  for (const n of [budget, held, tf]) assert.doesNotMatch(`${n.title} ${n.why} ${n.next}`, /POL-|A-ACCESS|제\d+조/)
  const unknown = noticeOf({ status: 'REJECTED', reason_code: 'SOMETHING_NEW', decided_at: null })
  assert.equal(unknown.title, '이번 요청은 진행할 수 없어요')
  const noMemo = noticeOf({ status: 'REJECTED', reason_code: 'ELIGIBLE', decided_at: '2026-10-21T05:23:17Z', decision_reason: '' })
  assert.match(noMemo.next, /이유를 물어본/)
})
