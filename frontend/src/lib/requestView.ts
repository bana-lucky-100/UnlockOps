import type { Problem, Status } from '../api'
import { doneKind, DONE_TEXT, isGuidanceComplete, isLegacyBudgetHold, stepText } from './status.ts'

/**
 * 요청자 화면에 무엇을 보여줄지 정하는 규칙을 한곳에 둔다 (명세: 화면별 명세 · 판단 근거는 승인자에게만).
 * - REJECTED · 실제 MANUAL_REVIEW에서는 reason_code별 문구(이유 한 줄 + 다음에 할 일)를 쓴다.
 *   이유는 쉬운 말로만 쓰고 규정 번호 · 판단 근거 원문은 넣지 않는다 (근거 원문은 승인자에게만).
 * - 승인자가 거절한 경우는 승인자 메모(decision_reason)를 그대로 보여준다.
 * - 서버 message · diagnosis는 표시용 문장일 뿐이라(규격: 상태 판정에 쓰지 않음) 화면 문구는 reason_code로 만든다.
 *   모르는 사유 코드일 때만 서버 문장으로 대신한다.
 */

export type StageKind = 'done' | 'cur' | 'todo' | 'review' | 'fail'
export interface Stage { label: string; sub: string; kind: StageKind }

const LABELS = ['요청 접수', '판단안', '승인', '권한 부여', '반영 확인'] as const

function stages(kinds: StageKind[], subs: string[]): Stage[] {
  return LABELS.map((label, i) => ({ label, kind: kinds[i], sub: subs[i] ?? '' }))
}

/** 승인자가 결정해서 거절된 것인지(사람) 규정 · 예산으로 바로 거절된 것인지(AI). */
export function rejectedByApprover(p: Problem) {
  return p.status === 'REJECTED' && (!!p.decided_at || p.reason_code === 'HUMAN_REJECTED')
}

/** 대상 이름이 없어서 담당자 검토로 넘어간 경우. 요청자가 이름을 넣어 다시 보내면 풀린다. */
export function needsName(p: Problem) {
  return p.status === 'MANUAL_REVIEW' && p.reason_code === 'RESOURCE_NOT_UNIQUE'
}

export function stagesOf(p: Problem): Stage[] {
  if (isGuidanceComplete(p)) return [
    { label: '요청 접수', sub: '', kind: 'done' },
    { label: '판단안', sub: '분석 완료', kind: 'done' },
    { label: '안내 제공', sub: '안내 완료', kind: 'done' },
  ]
  const s: Status = p.status
  switch (s) {
    case 'RECEIVED': return stages(['cur', 'todo', 'todo', 'todo', 'todo'], ['접수됨', '', '승인자 검토', '자동 부여', '다시 조회해 확인'])
    case 'DIAGNOSING': return stages(['done', 'cur', 'todo', 'todo', 'todo'], ['', '작성 중', '승인자 검토', '자동 부여', '다시 조회해 확인'])
    case 'WAITING_APPROVAL': return stages(['done', 'done', 'cur', 'todo', 'todo'], ['', '판단안 완료', stepText(p) ? `${stepText(p)} 승인 대기` : '승인자 검토 중', '자동 부여', '다시 조회해 확인'])
    case 'ON_HOLD': return p.reason_code === 'HELD_BY_APPROVER'
      ? stages(['done', 'done', 'review', 'todo', 'todo'], ['', '판단안 완료', '승인자 보류', '', ''])
      : stages(['done', 'review', 'todo', 'todo', 'todo'], ['', p.reason_code === 'BUDGET_INSUFFICIENT' ? '보류 · 예산 부족' : '보류', '', '', ''])
    case 'EXECUTING': return stages(['done', 'done', 'done', 'cur', 'todo'], ['', '판단안 완료', '승인됨', '부여 중', '다시 조회해 확인'])
    case 'DONE': return doneKind(p) === 'VERIFIED'
      ? stages(['done', 'done', 'done', 'done', 'done'], ['', '판단안 완료', '승인됨', '부여 완료', '다시 조회 ✓'])
      : stages(['done', 'done', 'done', 'done', 'done'], ['', '이미 권한 있음', '필요 없음', '필요 없음', '다시 조회 ✓'])
    case 'REJECTED': if (isLegacyBudgetHold(p)) return stages(['done', 'review', 'todo', 'todo', 'todo'], ['', '보류 · 예산 부족', '', '', ''])
      return rejectedByApprover(p)
      ? stages(['done', 'done', 'fail', 'todo', 'todo'], ['', '판단안 완료', '승인자 거절', '', ''])
      : stages(['done', 'fail', 'todo', 'todo', 'todo'], ['', '거절', '', '', ''])
    case 'MANUAL_REVIEW': return stages(['done', 'review', 'todo', 'todo', 'todo'], ['', needsName(p) ? '대상 이름 필요' : isLegacyBudgetHold(p) ? '보류 · 예산 부족' : '담당자가 확인 중', '', '', ''])
    case 'FAILED': return stages(['done', 'done', 'done', 'fail', 'todo'], ['', '판단안 완료', '승인됨', '부여 실패', '반영 안 됨'])
  }
}

export function summaryOf(p: Problem): string {
  if (isGuidanceComplete(p)) return '안내가 완료됐어요.'
  switch (p.status) {
    case 'RECEIVED': return '요청을 받았어요. 곧 AI가 확인을 시작해요.'
    case 'DIAGNOSING': return 'AI가 규정 근거와 부서 예산 영향을 정리하고 있어요. 이 화면을 닫아도 계속 진행돼요.'
    case 'WAITING_APPROVAL': return stepText(p)
      ? `판단안이 만들어졌어요. 지금 ${stepText(p)} 승인을 기다리고 있어요. 모든 단계가 승인되면 바로 부여돼요.`
      : '판단안이 만들어졌어요. 승인자가 근거와 예산 영향을 보고 결정하면 바로 부여돼요.'
    case 'ON_HOLD': return (reasonOf(p)?.title ?? '요청이 보류됐어요') + '. 다시 검토되는 조건을 확인해 주세요.'
    case 'EXECUTING': return '승인됐어요. 권한을 넣고 다시 조회해 확인하고 있어요.'
    case 'DONE': return ({
      VERIFIED: '권한 부여 완료. 다시 조회해 반영을 확인했어요.',
      ALREADY_HAS_ACCESS: DONE_TEXT.ALREADY_HAS_ACCESS.headline + '. 바꾼 것은 없어요.',
      SCAN_COMPLETED: DONE_TEXT.SCAN_COMPLETED.headline + '. 새로 찾은 후보를 담당자에게 알렸어요.',
      NO_NEW_CANDIDATES: DONE_TEXT.NO_NEW_CANDIDATES.headline + '. 이미 알린 후보는 다시 알리지 않아요.',
    } as Record<string, string>)[doneKind(p)] ?? '완료됐어요.'
    case 'REJECTED': return rejectedByApprover(p)
      ? '승인자가 이번 요청을 거절했어요. 메모를 확인해 주세요.'
      : (reasonOf(p)?.title ?? '이번 요청은 진행할 수 없어요') + '. 이유와 다음에 할 일을 확인해 주세요.'
    case 'MANUAL_REVIEW': return needsName(p)
      ? '어떤 저장소 · 프로젝트인지 알 수 없어 확인이 멈췄어요. 이름을 넣어 다시 보내 주세요.'
      : (reasonOf(p) ? reasonOf(p)!.title + '. 이유를 확인해 주세요.' : '요청 내용만으로는 필요한 권한을 정하기 어려워 담당자가 확인하고 있어요.')
    case 'FAILED': return '승인됐지만 권한을 넣지 못했어요. 운영 담당자가 확인하고 있어요.'
  }
}

/**
 * 판단안 말풍선. 서버 문장(합니다체 고정 문구) 대신 reason_code로 해요체 문장을 만든다.
 * - 요청자: 거절 · 보류 · 담당자 검토에서는 숨긴다(오른쪽 안내 카드가 이유와 다음 할 일을 맡는다).
 * - 승인자: 모든 상태에서 판단 이유를 보여 준다.
 * 모르는 사유 코드면 서버 문장(diagnosis)을 그대로 쓴다.
 */
export function judgmentOf(p: Problem, forApprover: boolean): string | null {
  // 안내 성공은 안내마다 내용이 달라서 서버 문장을 그대로 둔다(본문은 안내 내용 카드).
  if (isGuidanceComplete(p)) return p.diagnosis?.trim() || null
  if (!forApprover && (p.status === 'REJECTED' || p.status === 'ON_HOLD' || p.status === 'MANUAL_REVIEW')) return null
  const r = reasonOf(p)
  // 여러 단계 결재의 중간 단계에서는 '승인하면 바로 부여'가 아니다.
  if (forApprover && p.reason_code === 'ELIGIBLE' && isMidStep(p)) return '규정과 예산 조건을 모두 충족해요. 승인하면 다음 단계 승인자에게 넘어가요.'
  if (r) return (forApprover ? r.approver : r.requester) ?? r.why
  return p.diagnosis?.trim() || null
}
/** 여러 단계 결재에서 아직 마지막 단계가 아닌지(승인해도 바로 부여되지 않음). */
export function isMidStep(p: Pick<Problem, 'current_step' | 'total_steps'>): boolean {
  return !!p.current_step && (p.total_steps ?? 0) > p.current_step
}
/** 요청자 화면용(기존 이름 유지). */
export function aiMessageOf(p: Problem): string | null {
  return judgmentOf(p, false)
}

/** 안내 성공은 API 본문을 사용하고, 권한 부여 제안은 계획(플랫폼 · 역할)으로 만든다. */
export function proposalOf(p: Problem, platformLabel: string): string | null {
  if (isGuidanceComplete(p)) return p.proposal?.trim() || null
  if (!p.requested_role) return null
  if (!['WAITING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED'].includes(p.status)) return null
  if (p.status === 'DONE' && !p.decided_at) return null
  return `${platformLabel} ${p.requested_role} 권한을 부여하는 판단안이에요.`
}

/** nextLabel: 요청자가 직접 할 일이 있으면 '다음에 할 일', 기다리기만 하면 되는 경우는 '안내'. why: 이유 한 줄(규정 번호 없이). */
export interface Notice { tone: 'bad' | 'review'; title: string; memo: string | null; why?: string | null; nextLabel: string; next: string; resend?: boolean }

/**
 * reason_code별 문구. 공통 상태·사유 규격(테스트 시나리오 문서 4절) 24개 + 에이전트 규칙(rules.py)의 세부 코드.
 * 이유는 요청자가 이해할 수 있는 말로만 쓰고, 규정 번호 · 원문은 넣지 않는다.
 * - title / why / next: 요청자 안내 카드(거절 · 보류 · 담당자 검토 · 실패)
 * - requester / approver: 판단안 말풍선에 쓰는 한 문장(없으면 why)
 * - wait: 요청자는 기다리기만 하면 되는 경우(담당자가 처리)
 */
interface Reason { tone: 'bad' | 'review'; title: string; why: string; next: string; wait?: boolean; requester?: string; approver?: string }
const WAIT = '확인이 끝나면 이 화면과 홈에서 알려드릴게요'
const OK = { tone: 'review' as const, next: WAIT, wait: true }
export const REASONS: Record<string, Reason> = {
  // 승인 대기 · 진행
  ELIGIBLE:                 { ...OK, title: '승인 조건을 충족해요', why: '규정과 예산 조건을 모두 충족해요.',
                              requester: '규정과 예산 조건을 모두 충족해서 승인자에게 보냈어요.', approver: '규정과 예산 조건을 모두 충족해요. 승인하면 바로 부여돼요.' },
  LEAST_PRIVILEGE_PROPOSED: { ...OK, title: '더 낮은 권한으로 제안했어요', why: '요청한 권한보다 낮은 권한으로도 업무가 가능해 그 권한으로 판단안을 만들었어요.',
                              requester: '말씀하신 업무에는 더 낮은 권한으로 충분해서, 그 권한으로 승인자에게 보냈어요.', approver: '요청보다 낮은 최소 권한으로 판단안을 만들었어요. 요청 원래 권한은 부여하지 않아요.' },
  HUMAN_APPROVED:           { ...OK, title: '모든 단계가 승인됐어요', why: '모든 승인 단계가 끝나 권한을 넣고 있어요.' },
  // 보류
  BUDGET_INSUFFICIENT:      { tone: 'review', title: '부서 예산이 부족해 보류됐어요', why: '부서 잔여 예산이 이 권한의 월 비용보다 적어요.', next: '부서장에게 예산 증액을 요청해 주세요. 예산이 확보되면 다시 검토해요',
                              approver: '부서 잔여 예산이 이 권한의 월 비용보다 적어 보류했어요. 예산이 확보되면 다시 검토해요.' },
  HELD_BY_APPROVER:         { tone: 'review', title: '승인자가 보류했어요', why: '승인자가 확인할 내용이 있어 결정을 미뤘어요.', next: '승인자가 남긴 메모를 확인해 주세요. 보류가 풀리면 다시 검토해요',
                              approver: '승인자가 사유를 남기고 보류했어요. 보류가 풀리면 최신 규정과 예산으로 다시 검토해요.' },
  // 거절
  HUMAN_REJECTED:           { tone: 'bad', title: '승인자가 거절했어요', why: '승인자가 이번 요청을 승인하지 않았어요.', next: '메모를 확인하고, 필요하면 내용을 보완해 다시 요청하세요' },
  POLICY_NOT_ELIGIBLE:      { tone: 'bad', title: '신청 자격이 없는 권한이에요', why: '이 권한은 직군이나 신청 자격이 정해져 있어요.', next: '업무에 꼭 필요하면 부서장과 상의해 주세요' },
  NOT_TF_MEMBER:            { tone: 'bad', title: '아직 TF 명단에 없어요', why: 'TF 전용 자원은 TF 구성원만 쓸 수 있어요.', next: 'TF 리더에게 구성원 등록을 먼저 요청한 뒤 다시 보내 주세요' },
  DUPLICATE_SEAT:           { tone: 'bad', title: '이미 같은 유료 좌석이 있어요', why: '같은 유료 좌석을 두 번 사면 비용만 늘어서 추가로 드리지 않아요.', next: '그래도 안 되면 로그아웃 후 다시 로그인해 보세요' },
  NON_DEV_SEAT:             { tone: 'bad', title: '개발 직무만 신청할 수 있는 유료 권한이에요', why: '유료 개발 도구는 개발 직무 구성원에게만 부여해요.', next: '업무에 꼭 필요하면 부서장과 상의해 주세요' },
  FORBIDDEN_ADMIN:          { tone: 'bad', title: '관리자 권한은 여기서 드릴 수 없어요', why: '관리자 · 소유자 · 전체 접근 권한은 보안 위험이 커서 별도 절차로만 처리해요.', next: '꼭 필요하면 IT 보안팀에 따로 요청해 주세요' },
  ABOVE_ACCESS_CEILING:     { tone: 'bad', title: '요청한 권한이 허용 범위보다 높아요', why: '직무와 직급에 따라 받을 수 있는 권한의 상한이 정해져 있어요.', next: '더 낮은 권한으로 다시 요청하거나 부서장과 상의해 주세요' },
  CONFIDENTIAL_DEPARTMENT:  { tone: 'bad', title: '지정된 부서만 볼 수 있는 문서예요', why: '기밀 문서는 지정 부서 구성원만 열 수 있어요.', next: '필요하면 부서장에게 문의해 주세요' },
  DEPARTMENT_MISMATCH:      { tone: 'bad', title: '다른 부서 전용 문서예요', why: '이 문서는 해당 부서 구성원만 볼 수 있어요.', next: '문서를 관리하는 부서에 공유를 요청해 주세요' },
  // 담당자 검토
  MISSING_SOURCE_EVIDENCE:  { tone: 'review', title: '규정 근거를 다시 확인하고 있어요', why: '판단에 필요한 규정 근거를 찾지 못해 자동으로 진행하지 않았어요.', next: WAIT, wait: true },
  APPROVER_UNAVAILABLE:     { tone: 'review', title: '승인자를 정하지 못했어요', why: '지정할 수 있는 승인자가 없거나 요청자 본인이 승인자예요. 승인자를 추측해 정하지 않아요.', next: WAIT, wait: true },
  OUT_OF_SCOPE:             { tone: 'review', title: '자동 처리 범위 밖의 요청이에요', why: '이 서비스가 자동으로 처리하는 권한 요청이 아니어서 담당자에게 넘겼어요.', next: '담당자가 확인해 안내해 드릴게요', wait: true },
  REQUEST_OUT_OF_SCOPE:     { tone: 'review', title: '자동 처리 범위 밖의 요청이에요', why: '이 서비스가 자동으로 처리하는 권한 요청이 아니어서 담당자에게 넘겼어요.', next: '담당자가 확인해 안내해 드릴게요', wait: true },
  BUDGET_UNAVAILABLE:       { tone: 'review', title: '예산을 확인하지 못해 담당자가 보고 있어요', why: '부서 예산 정보가 없어 비용 판단을 할 수 없었어요.', next: WAIT, wait: true },
  MODEL_UNAVAILABLE:        { tone: 'review', title: 'AI 판단이 잠시 어려워 담당자가 보고 있어요', why: '판단안을 만드는 AI가 응답하지 않아 담당자에게 넘겼어요.', next: WAIT, wait: true },
  UNSUPPORTED_ROLE:         { tone: 'review', title: '자동으로 판단할 수 없는 권한이에요', why: '이 권한은 자동 처리 기준이 없어 담당자가 직접 판단해요.', next: WAIT, wait: true },
  JIRA_SCHEME_MISMATCH:     { tone: 'review', title: '프로젝트 설정 확인이 필요해요', why: '프로젝트 역할은 있지만 조회 권한이 없어 권한 설정을 담당자가 확인해요.', next: WAIT, wait: true },
  EDIT_OUT_OF_DEMO_SCOPE:   { tone: 'review', title: '편집 권한은 담당자가 직접 처리해요', why: '문서 편집 권한은 자동 부여 범위 밖이에요.', next: WAIT, wait: true },
  POLICY_EVIDENCE_MISMATCH: { tone: 'review', title: '규정 근거를 다시 확인하고 있어요', why: '규정 문서와 근거가 일치하는지 확인되지 않아 자동으로 진행하지 않았어요.', next: WAIT, wait: true },
  POLICY_SOURCE_UNAVAILABLE:{ tone: 'review', title: '규정 문서를 불러오지 못했어요', why: '규정 원문을 확인할 수 없어 자동으로 진행하지 않았어요.', next: WAIT, wait: true },
  // 완료
  VERIFIED:                 { ...OK, title: '권한 부여 완료', why: '권한을 넣고 다시 조회해 반영을 확인했어요.' },
  ALREADY_HAS_ACCESS:       { ...OK, title: '이미 권한이 있어요', why: '조회 결과 필요한 권한을 이미 보유하고 있어요. 바꾼 것은 없어요.' },
  RAG_GUIDANCE:             { ...OK, title: '안내 완료', why: '규정 근거를 확인해 해결 방법을 안내했어요.' },
  SCAN_IN_PROGRESS:         { ...OK, title: '점검 결과를 정리하고 있어요', why: '회수 후보를 저장하고 담당자에게 알리고 있어요.' },
  SCAN_COMPLETED:           { ...OK, title: '회수 후보 점검 완료', why: '새로 찾은 회수 후보를 담당자에게 알렸어요.' },
  NO_NEW_CANDIDATES:        { ...OK, title: '신규 회수 후보 없음', why: '새로 찾은 회수 후보가 없어요. 이미 알린 후보는 다시 알리지 않아요.' },
  // 실패
  VERIFICATION_FAILED:      { tone: 'bad', title: '권한이 반영되지 않았어요', why: '권한을 넣은 뒤 다시 조회했는데 반영이 확인되지 않았어요.', next: '운영 담당자가 확인하고 있어요. 처리되면 이 화면과 홈에서 알려드릴게요', wait: true },
  TOOL_CALL_FAILED:         { tone: 'bad', title: '연결 문제로 처리하지 못했어요', why: '조회하거나 권한을 넣는 중에 연결 문제가 생겼어요.', next: '운영 담당자가 확인하고 있어요. 처리되면 이 화면과 홈에서 알려드릴게요', wait: true },
  SCAN_FAILED:              { tone: 'bad', title: '회수 점검을 하지 못했어요', why: '점검 실행 중 오류가 나서 끝까지 진행하지 못했어요.', next: '다시 점검하거나 다음 정기 점검을 기다려 주세요' },
  NOTIFICATION_FAILED:      { tone: 'bad', title: '회수 후보 알림을 보내지 못했어요', why: '후보는 찾았지만 담당자 알림이 다시 시도해도 실패했어요.', next: '다시 점검하면 알림을 다시 보내요' },
}
export function reasonOf(p: Pick<Problem, 'reason_code'>): Reason | null {
  return (p.reason_code && REASONS[p.reason_code]) || null
}

/** 오른쪽 안내 카드. 판단 근거(규정 번호 · 판단 주체)는 넣지 않는다. */
export function noticeOf(p: Problem): Notice | null {
  if (isGuidanceComplete(p)) return null
  if (p.status === 'REJECTED') {
    const memo = p.decision_reason?.trim() || null
    if (rejectedByApprover(p)) return memo
      ? { tone: 'bad', title: '승인자가 거절했어요', memo, nextLabel: '다음에 할 일', next: '메모를 확인하고, 필요하면 내용을 보완해 다시 요청하세요' }
      : { tone: 'bad', title: '승인자가 거절했어요', memo: null, nextLabel: '다음에 할 일', next: '남긴 메모가 없어요. 승인자에게 이유를 물어본 뒤 보완해 다시 요청하세요' }
    const r = reasonOf(p)
    return r
      ? { tone: r.tone, title: r.title, memo: null, why: r.why, nextLabel: r.wait ? '안내' : '다음에 할 일', next: r.next }
      : { tone: 'bad', title: '이번 요청은 진행할 수 없어요', memo: null, nextLabel: '다음에 할 일', next: '업무에 꼭 필요하면 승인자에게 문의하세요' }
  }
  if (p.status === 'ON_HOLD') {
    const r = reasonOf(p) ?? REASONS.HELD_BY_APPROVER
    const memo = p.reason_code === 'HELD_BY_APPROVER'
      ? (p.decision_reason?.trim() || p.approval_steps?.find(x => x.status === 'ON_HOLD')?.reason?.trim() || null) : null
    return { tone: 'review', title: r.title, memo, why: r.why, nextLabel: '다시 검토되는 조건', next: r.next }
  }
  // 이름이 없어서 대상을 정하지 못한 경우는 요청자가 이름을 넣어 다시 보내면 바로 풀린다.
  if (needsName(p)) return { tone: 'review', title: '어떤 대상인지 알려 주세요', memo: null, nextLabel: '다음에 할 일', next: '저장소 · 프로젝트 · 채널 · 페이지 이름을 넣어 다시 보내 주세요. AI가 바로 다시 확인해요', resend: true }
  if (p.status === 'MANUAL_REVIEW') {
    const r = reasonOf(p)
    return r
      ? { tone: r.tone, title: r.title, memo: null, why: r.why, nextLabel: r.wait ? '안내' : '다음에 할 일', next: r.next }
      : { tone: 'review', title: '담당자가 확인하고 있어요', memo: null, why: '요청 내용만으로는 필요한 권한을 정하기 어려웠어요.', nextLabel: '안내', next: WAIT }
  }
  if (p.status === 'FAILED' && reasonOf(p)) { const r = reasonOf(p)!; return { tone: 'bad', title: r.title, memo: null, why: r.why, nextLabel: '안내', next: r.next } }
  if (p.status === 'FAILED') return { tone: 'bad', title: '부여 실패 · 운영 담당자 확인 중', memo: null, nextLabel: '안내', next: '처음 시도를 포함해 총 3번 시도했어요. 처리되면 이 화면과 홈에서 알려드릴게요. 다른 플랫폼 요청에는 영향이 없어요' }
  return null
}

/* ---------- 승인자에게만 보이는 것 (명세: 판단 근거는 승인자에게만) ---------- */

export interface EvidenceDoc { id: string; parts: { article: string; text: string }[] }
export interface EvidenceFact { k: string; v: string }

const FAMILY: Record<string, string> = { DEV: '개발', NON_DEV: '비개발' }

/**
 * evidence 배열(RAG 조각 + 직원 사실)을 승인자가 읽기 쉬운 두 묶음으로 나눈다.
 * - facts: Business MCP가 조회한 직원 사실(소속 · TF · 현재 권한 · 허용 상한)
 * - docs: 같은 문서(POL-03, A-ACCESS-04 …)끼리 모은 규정 원문
 */
export function evidenceOf(p: Problem): { facts: EvidenceFact[]; docs: EvidenceDoc[] } {
  const list = Array.isArray(p.evidence) ? p.evidence : []
  const raw = list.find(e => e.kind === 'employee_facts') as Record<string, unknown> | undefined
  const facts: EvidenceFact[] = []
  if (raw) {
    const who = [raw.department, raw.grade, FAMILY[String(raw.job_family)] ?? raw.job_family].filter(Boolean).join(' · ')
    if (who) facts.push({ k: '요청자 소속', v: who })
    facts.push({ k: 'TF 구성원', v: raw.tf_member ? '예' : '아니요' })
    facts.push({ k: '현재 권한', v: raw.current_role ? String(raw.current_role) : '없음' })
    if (raw.maximum_role) facts.push({ k: '규정상 허용 상한', v: String(raw.maximum_role) })
  }
  const docs = new Map<string, EvidenceDoc>()
  for (const e of list) {
    if (typeof e.doc_id !== 'string' || typeof e.text !== 'string' || !e.text.trim()) continue
    const doc = docs.get(e.doc_id) ?? { id: e.doc_id, parts: [] }
    const article = typeof e.article === 'string' && /^제\d+조$/.test(e.article) ? e.article : ''
    if (!doc.parts.some(x => x.text === e.text)) doc.parts.push({ article, text: e.text.trim() })
    docs.set(e.doc_id, doc)
  }
  // 회사 규정(POL)을 먼저, 접근 권한표(A-ACCESS)를 뒤에.
  const order = (id: string) => (id.startsWith('POL') ? 0 : 1)
  return { facts, docs: [...docs.values()].sort((a, b) => order(a.id) - order(b.id) || a.id.localeCompare(b.id)) }
}

export function requesterEventsOf(p: Problem): { at: string; text: string }[] {
  return (p.events ?? []).map(e => ({
    at: e.created_at,
    text: typeof e.payload?.message === 'string' ? e.payload.message : '',
  })).filter(e => e.text)
}

/** 승인자는 원본 이벤트를 받는다. 요청자 화면과 같은 말투의 짧은 문장으로 바꾼다. */
export function approverEventsOf(p: Problem): { at: string; text: string }[] {
  const STATUS_TEXT: Partial<Record<Status, string>> = {
    WAITING_APPROVAL: 'AI가 판단안을 만들어 승인을 요청했어요',
    MANUAL_REVIEW: '담당자 검토가 필요하다고 판단했어요',
    REJECTED: '규정상 자동으로 줄 수 없어 거절됐어요',
    ON_HOLD: '보류됐어요',
    DONE: '다시 조회해 반영을 확인했어요',
    FAILED: '권한을 넣지 못했어요',
  }
  const out: { at: string; text: string }[] = []
  let prev = ''
  for (const e of p.events ?? []) {
    const pl = (e.payload ?? {}) as Record<string, unknown>
    const result = pl.result as Record<string, unknown> | undefined
    // Historical audit envelopes remain immutable; current Problem status never uses this fallback.
    const guidance = result && (
      (result.status === 'DONE' && result.result_type === 'GUIDANCE') ||
      (!('result_type' in result) && result.status === 'MANUAL_REVIEW' && result.reasonCode === 'RAG_GUIDANCE'
        && typeof result.proposal === 'string' && !!result.proposal.trim() && !result.plan && result.verification_ok == null)
    )
    const text = e.kind === 'PROGRESS' ? (pl.job_type === 'EXECUTE' ? '권한을 넣고 있어요' : 'AI가 요청을 분석하고 있어요')
      : e.kind === 'HUMAN_DECISION' ? (pl.approved ? '승인했어요' : '거절했어요')
      : (e.kind === 'ANALYZED' || e.kind === 'EXECUTED') && result ? (guidance ? '안내가 완료됐어요' : STATUS_TEXT[result.status as Status] ?? '')
      : e.kind === 'FAILED' ? '처리하지 못해 운영 담당자 확인이 필요해요'
      : ''
    if (!text || text === prev) continue
    out.push({ at: e.created_at, text })
    prev = text
  }
  return out
}

/** 거절 사유 칩. 고른 칩과 직접 쓴 문장을 합쳐 decision_reason으로 보낸다. */
export const REJECT_CHIPS = ['업무에 필요하지 않음', '더 낮은 권한으로 충분', '보안 검토 필요'] as const

/**
 * 승인자(운영 담당자 포함)가 보는 오른쪽 안내. 요청자용 문구("이름을 넣어 다시 보내 주세요")를
 * 승인자에게 그대로 보이면 누구에게 하는 말인지 헷갈린다.
 * 담당자 검토를 이 화면에서 처리하는 API는 아직 없어서, 지금 할 수 있는 일만 안내한다.
 */
export function approverNoticeOf(p: Problem): { tone: 'bad' | 'review'; title: string; body: string } | null {
  if (isGuidanceComplete(p)) return null
  if (needsName(p)) return { tone: 'review', title: '대상이 정해지지 않은 요청이에요', body: '요청자가 저장소 · 프로젝트 이름을 적지 않아 AI가 대상을 정하지 못했어요. 요청자에게는 이름을 넣어 다시 보내도록 안내하고 있고, 다시 보내면 새 요청으로 승인함에 올라와요.' }
  if (p.status === 'ON_HOLD') return { tone: 'review', title: p.reason_code === 'HELD_BY_APPROVER' ? '보류한 요청이에요' : '예산 부족으로 보류된 요청이에요',
    body: p.reason_code === 'HELD_BY_APPROVER' ? '보류 사유가 해소되면 최신 규정과 예산으로 다시 검토해요. 기존 승인은 요청 범위가 그대로일 때만 이어져요.' : '부서 예산이 확보되면 최신 규정과 예산으로 다시 검토해요. 지금은 승인할 수 없어요.' }
  if (p.status === 'MANUAL_REVIEW') return { tone: 'review', title: '담당자 확인이 필요한 요청이에요', body: 'AI가 자동으로 판단하지 못했어요. 왼쪽의 진단과 판단 근거를 확인해 주세요. 이 화면에서 바로 처리하는 기능은 아직 없어요.' }
  if (p.status === 'FAILED') return { tone: 'bad', title: '권한 부여에 실패했어요', body: '승인 뒤 처음 시도를 포함해 총 3번 시도했지만 권한을 넣지 못했어요. 대상 플랫폼의 상태를 확인해 주세요.' }
  if (p.status === 'REJECTED' && !p.decided_at) return { tone: 'bad', title: '규정상 자동으로 거절된 요청이에요', body: '거절 이유는 왼쪽 판단 근거에서 확인할 수 있어요. 요청자에게는 이유 대신 승인자에게 문의하라고 안내돼요.' }
  return null
}

export function approverSummaryOf(p: Problem): string {
  if (isGuidanceComplete(p)) return summaryOf(p)
  if (needsName(p)) return '요청자가 대상 이름을 적지 않아 AI가 대상을 정하지 못했어요.'
  if (p.status === 'ON_HOLD') return (reasonOf(p)?.title ?? '보류된 요청이에요') + '.'
  if (p.status === 'MANUAL_REVIEW') return 'AI가 자동으로 판단하지 못해 담당자 확인이 필요해요.'
  if (p.status === 'REJECTED' && !p.decided_at) return '규정에 맞지 않아 AI가 바로 거절했어요.'
  return summaryOf(p)
}
