import test from 'node:test'
import assert from 'node:assert/strict'
import { groupOf, isGuidanceComplete, needsRefresh, statusOf } from '../src/lib/status.ts'
import {
  aiMessageOf, approverEventsOf, approverNoticeOf, approverSummaryOf,
  noticeOf, proposalOf, requesterEventsOf, stagesOf, summaryOf,
} from '../src/lib/requestView.ts'

// API가 기존 계약으로 반환하는 안내 성공: 권한 부여 계획이나 실행 영수증은 없다.
const guidance = {
  status: 'MANUAL_REVIEW', reason_code: 'RAG_GUIDANCE',
  diagnosis: '조회 결과 필요한 권한을 이미 보유하고 있습니다.',
  proposal: '조회한 현재 권한은 Write입니다.\n\n1. push는 Write 이상이 필요합니다.\n근거: GH-OFF-01:summary',
  resource_id: null, requested_role: null, verification_ok: null, decided_at: null,
  events: [
    { kind: 'PROGRESS', payload: { message: '요청을 분석하고 있습니다.' }, created_at: '2026-10-21T05:23:16Z' },
    { kind: 'ANALYZED', payload: { message: '담당자 검토가 필요합니다.' }, created_at: '2026-10-21T05:23:17Z' },
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
  const rawResult = { status: 'MANUAL_REVIEW', reasonCode: 'RAG_GUIDANCE' }
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
  assert.equal(rawResult.status, 'MANUAL_REVIEW')
})

test('missing guidance or genuine manual review never becomes a successful completion', () => {
  for (const patch of [
    { proposal: undefined }, { proposal: null }, { proposal: ' \n ' },
    { reason_code: 'RESOURCE_NOT_UNIQUE' }, { reason_code: 'ANSWER_NOT_GROUNDED' },
    { reason_code: 'MODEL_UNAVAILABLE' }, { reason_code: undefined },
  ]) {
    const problem = { ...guidance, ...patch }
    assert.equal(isGuidanceComplete(problem), false)
    assert.equal(statusOf(problem).label, '담당자 검토')
    assert.equal(groupOf(problem), 'waiting')
    assert.equal(needsRefresh(problem), true)
    assert.equal(aiMessageOf(problem), null)
    assert.equal(proposalOf(problem, 'GitHub'), null)
    assert.ok(noticeOf(problem))
    assert.ok(approverNoticeOf(problem))
  }
})

test('guidance content cannot override pending, rejected, or failed workflow states', () => {
  for (const status of ['RECEIVED', 'DIAGNOSING', 'WAITING_APPROVAL', 'EXECUTING', 'REJECTED', 'FAILED']) {
    assert.equal(isGuidanceComplete({ ...guidance, status }), false)
  }
  const waiting = { status: 'WAITING_APPROVAL', requested_role: 'Write' }
  assert.equal(groupOf(waiting), 'waiting')
  assert.equal(needsRefresh(waiting), true)
  assert.equal(proposalOf(waiting, 'GitHub'), 'GitHub에서 Write 권한을 주면 해결돼요.')
  const granted = { status: 'DONE', requested_role: 'Write', verification_ok: true, decided_at: '2026-10-21T05:23:17Z' }
  assert.equal(statusOf(granted).label, '완료')
  assert.equal(groupOf(granted), 'finished')
  assert.equal(needsRefresh(granted), false)
  assert.match(summaryOf(granted), /권한이 열렸어요/)
  assert.equal(stagesOf(granted).at(-1).label, '반영 확인')
})
