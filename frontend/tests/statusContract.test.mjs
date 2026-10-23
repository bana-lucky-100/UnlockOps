import test from 'node:test'
import assert from 'node:assert/strict'
import { groupOf, isOnHold, statusOf } from '../src/lib/status.ts'
import { approverNoticeOf, judgmentOf, noticeOf, REASONS, stagesOf, summaryOf } from '../src/lib/requestView.ts'

// 테스트 시나리오 문서 · 공통 상태·사유 규격 4절의 사유 코드 24개
const SPEC_CODES = ['ELIGIBLE', 'LEAST_PRIVILEGE_PROPOSED', 'BUDGET_INSUFFICIENT', 'HELD_BY_APPROVER', 'HUMAN_APPROVED', 'HUMAN_REJECTED',
  'POLICY_NOT_ELIGIBLE', 'NOT_TF_MEMBER', 'DUPLICATE_SEAT', 'MISSING_SOURCE_EVIDENCE', 'APPROVER_UNAVAILABLE', 'OUT_OF_SCOPE',
  'BUDGET_UNAVAILABLE', 'MODEL_UNAVAILABLE', 'VERIFIED', 'ALREADY_HAS_ACCESS', 'RAG_GUIDANCE', 'SCAN_IN_PROGRESS', 'SCAN_COMPLETED',
  'NO_NEW_CANDIDATES', 'VERIFICATION_FAILED', 'TOOL_CALL_FAILED', 'SCAN_FAILED', 'NOTIFICATION_FAILED']

test('규격 사유 코드 24개 모두 해요체 문구가 있다', () => {
  assert.equal(SPEC_CODES.length, 24)
  for (const code of SPEC_CODES) {
    const r = REASONS[code]
    assert.ok(r, code)
    for (const text of [r.title, r.why, r.requester, r.approver].filter(Boolean)) assert.doesNotMatch(text, /합니다|습니다/, code)
  }
})

test('ON_HOLD: 보류로 보이고 끝난 요청이 아니며, 다시 검토되는 조건을 알려 준다', () => {
  const p = { status: 'ON_HOLD', reason_code: 'BUDGET_INSUFFICIENT', decided_at: null }
  assert.equal(statusOf(p).label, '보류')
  assert.equal(statusOf(p).terminal, false)
  assert.equal(groupOf(p), 'waiting')
  assert.equal(isOnHold(p), true)
  assert.equal(stagesOf(p)[1].sub, '보류 · 예산 부족')
  const n = noticeOf(p)
  assert.equal(n.nextLabel, '다시 검토되는 조건')
  assert.match(n.next, /예산이 확보되면 다시 검토/)
  assert.equal(judgmentOf(p, false), null) // 요청자는 안내 카드로 본다
  assert.match(judgmentOf(p, true), /보류/)
  assert.ok(approverNoticeOf(p))
  const held = { status: 'ON_HOLD', reason_code: 'HELD_BY_APPROVER', decision_reason: '사용 기간 확인 필요' }
  assert.equal(stagesOf(held)[2].sub, '승인자 보류')
  assert.equal(noticeOf(held).memo, '사용 기간 확인 필요')
})

test('[임시] 서버가 ON_HOLD를 보내기 전 예산 부족 추측은 그대로 동작한다', () => {
  const legacy = { status: 'REJECTED', reason_code: 'BUDGET_INSUFFICIENT', decided_at: null }
  assert.equal(statusOf(legacy).label, '보류')
  assert.equal(isOnHold(legacy), true)
})

test('승인 대기는 여러 단계면 n/m단계를 함께 보여 준다', () => {
  const two = { status: 'WAITING_APPROVAL', reason_code: 'ELIGIBLE', current_step: 1, total_steps: 2 }
  assert.equal(statusOf(two).label, '1/2단계 승인 대기')
  assert.equal(stagesOf(two)[2].sub, '1/2단계 승인 대기')
  assert.match(summaryOf(two), /1\/2단계 승인을 기다리고/)
  assert.equal(statusOf({ status: 'WAITING_APPROVAL', current_step: 1, total_steps: 1 }).label, '승인 대기')
  assert.equal(statusOf({ status: 'WAITING_APPROVAL' }).label, '승인 대기')
})

test('완료는 사유별 문구로 나눈다 (회수 점검을 회수 완료로 쓰지 않는다)', () => {
  const label = reason_code => statusOf({ status: 'DONE', reason_code }).label
  assert.equal(label('VERIFIED'), '부여 완료')
  assert.equal(label('ALREADY_HAS_ACCESS'), '이미 보유')
  assert.equal(label('RAG_GUIDANCE'), '안내 완료')
  assert.equal(label('SCAN_COMPLETED'), '점검 완료')
  assert.equal(label('NO_NEW_CANDIDATES'), '신규 후보 없음')
  assert.match(summaryOf({ status: 'DONE', reason_code: 'ALREADY_HAS_ACCESS' }), /조회 결과 필요한 권한을 이미 보유하고 있어요/)
  for (const code of ['SCAN_COMPLETED', 'NO_NEW_CANDIDATES']) assert.doesNotMatch(summaryOf({ status: 'DONE', reason_code: code }), /회수 완료/)
})

test('판단 문장은 사유 코드로 만들고, 모르는 코드일 때만 서버 문장을 쓴다', () => {
  const p = { status: 'WAITING_APPROVAL', reason_code: 'ELIGIBLE', diagnosis: 'Write 부여 조건을 충족합니다.' }
  assert.equal(judgmentOf(p, false), REASONS.ELIGIBLE.requester)
  assert.equal(judgmentOf(p, true), REASONS.ELIGIBLE.approver)
  assert.equal(judgmentOf({ ...p, reason_code: 'SOMETHING_NEW' }, true), 'Write 부여 조건을 충족합니다.')
  // 2단계 중 1단계 승인자에게는 '바로 부여'라고 하지 않는다
  assert.match(judgmentOf({ ...p, current_step: 1, total_steps: 2 }, true), /다음 단계 승인자/)
  assert.equal(judgmentOf({ ...p, current_step: 2, total_steps: 2 }, true), REASONS.ELIGIBLE.approver)
})

test('회수 후보: 신규 · 이미 알린 후보는 notified_at으로, 유지 · 제외는 candidate_status로 나눈다', async () => {
  const { isNewInRun, isAlreadyNotified } = await import('../src/lib/revocation.ts')
  const run = { id: 'r', task_type: 'RECLAIM_SCAN', trigger: 'SCHEDULE', status: 'DONE', reason_code: 'SCAN_COMPLETED', started_at: '2026-10-22T00:00:00Z', finished_at: '2026-10-22T00:01:00Z' }
  const c = (candidate_status, notified_at) => ({ candidate_status, notified_at })
  assert.equal(isNewInRun(c('PENDING_REVIEW', '2026-10-22T00:00:30Z'), run), true)
  assert.equal(isAlreadyNotified(c('PENDING_REVIEW', '2026-10-21T00:00:30Z'), run), true)
  assert.equal(isNewInRun(c('PENDING_REVIEW', null), run), false) // 알림 성공 전에는 신규로 보지 않는다
  for (const s of ['RETAINED', 'EXCLUDED']) {
    assert.equal(isNewInRun(c(s, '2026-10-22T00:00:30Z'), run), false)
    assert.equal(isAlreadyNotified(c(s, '2026-10-21T00:00:30Z'), run), false)
  }
})

test('회수 점검: 일부만 조회된 실패는 후보를 보여 주고, 추가 확인 건수를 센다', async () => {
  const { isPartial, needsReviewCount } = await import('../src/lib/revocation.ts')
  const run = (status, reason_code) => ({ id: 'r', task_type: 'RECLAIM_SCAN', trigger: 'MANUAL', status, reason_code, started_at: 't', finished_at: null })
  const c = [{ candidate_status: 'PENDING_REVIEW', notified_at: null }]
  assert.equal(isPartial({ run: run('FAILED', 'SCAN_FAILED'), summary: { new_count: 0, monthly_saving: 0 }, candidates: c }), true)
  assert.equal(isPartial({ run: run('FAILED', 'SCAN_FAILED'), summary: { new_count: 0, monthly_saving: 0 }, candidates: [] }), false)
  assert.equal(isPartial({ run: run('FAILED', 'NOTIFICATION_FAILED'), summary: { new_count: 0, monthly_saving: 0 }, candidates: c }), false)
  assert.equal(needsReviewCount({ summary: { new_count: 0, monthly_saving: 0 }, candidates: [], needs_review: [{}, {}] }), 2)
  assert.equal(needsReviewCount({ summary: { new_count: 0, monthly_saving: 0, needs_review_count: 3 }, candidates: [] }), 3)
})

test('새 SaaS 코드나 모르는 코드가 와도 화면 정보가 있다 (M-1 Snowflake)', async () => {
  const { platformOf } = await import('../src/lib/platforms.ts')
  assert.equal(platformOf('SNOWFLAKE').label, 'Snowflake')
  assert.equal(platformOf('TABLEAU_CLOUD').label, 'Tableau Cloud')
  assert.equal(platformOf('TABLEAU').label, 'Tableau Cloud')
  assert.equal(platformOf('GITHUB').label, 'GitHub')
  assert.equal(platformOf('SOMETHING_NEW').label, 'SOMETHING_NEW')
  assert.ok(platformOf(undefined).icon)
})

test('권한 코드는 한국어 설명을 함께 쓰고, 모르는 코드는 코드만 둔다', async () => {
  const { roleText } = await import('../src/lib/platforms.ts')
  assert.equal(roleText('SNOWFLAKE', 'USAGE'), '웨어하우스 이용')
  assert.equal(roleText('GITHUB', 'Write'), '저장소 쓰기')
  assert.equal(roleText('DATADOG', 'Read Only'), '로그 · 대시보드 조회')
  assert.equal(roleText('SNOWFLAKE', 'OPERATE'), null)
  assert.equal(roleText('GITHUB', undefined), null)
})

test('회수 점검 v4: scan_complete=false면 일부 조회, 추가 확인은 새 필드와 예전 필드를 모두 읽는다', async () => {
  const { isPartial, needsReviewRow } = await import('../src/lib/revocation.ts')
  const run = { id: 'r', task_type: 'RECLAIM_SCAN', trigger: 'MANUAL', status: 'FAILED', reason_code: 'SCAN_FAILED', started_at: 't', finished_at: null }
  assert.equal(isPartial({ run, summary: { new_count: 0, monthly_saving: 0 }, candidates: [], scan_complete: false }), true)
  assert.deepEqual(needsReviewRow({ employee_name: '이운영', resource_name: 'Notion 팀 좌석', missing: ['LAST_USED_AT', 'NEW_CODE'] }),
    { who: '이운영', what: 'Notion 팀 좌석', missing: ['마지막 사용일', 'NEW_CODE'] })
  assert.equal(needsReviewRow({ user_name: '정데이터', platform: 'Tableau', missing: [] }).who, '정데이터')
})
