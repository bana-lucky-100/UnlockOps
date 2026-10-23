import type { Problem, Status } from '../api'

/**
 * 공통 상태 규격 9개의 화면 표기 (테스트 시나리오 문서 · 공통 상태·사유 규격).
 * 색: 진행 = 남보라, 확인 대기(승인 대기) = 주황, 사람이 볼 일(보류 · 담당자 검토) = 주황 + 사람 아이콘, 완료 = 초록, 거절 · 실패 = 빨강.
 * 프론트는 서버가 저장한 상태를 그대로 보여 주고 완료 여부를 추측하지 않는다(규격 6-8).
 */
export const STATUS: Record<Status, { label: string; tone: 'run'|'warn'|'review'|'ok'|'bad'; terminal: boolean }> = {
  RECEIVED:         { label: '접수',        tone: 'run',  terminal: false },
  DIAGNOSING:       { label: '판단안 작성 중', tone: 'run',  terminal: false },
  WAITING_APPROVAL: { label: '승인 대기',   tone: 'warn', terminal: false },
  ON_HOLD:          { label: '보류',        tone: 'review', terminal: false },
  EXECUTING:        { label: '부여 중',     tone: 'run',  terminal: false },
  DONE:             { label: '완료',        tone: 'ok',   terminal: true },
  REJECTED:         { label: '거절',        tone: 'bad',  terminal: true },
  MANUAL_REVIEW:    { label: '담당자 검토', tone: 'review', terminal: true },
  FAILED:           { label: '실패',        tone: 'bad',  terminal: true },
}

type StatusContext = Pick<Problem, 'status' | 'reason_code' | 'proposal'> & Partial<Pick<Problem, 'result_type' | 'decided_at' | 'current_step' | 'total_steps'>>

/** 완료 여부는 status, 완료 대상은 result_type으로 판단한다(#29). 사유 코드나 문구로 완료를 추측하지 않는다. */
export function isGuidanceComplete(p: StatusContext): boolean {
  return p.status === 'DONE' && p.result_type === 'GUIDANCE'
}

/**
 * [임시] 서버가 ON_HOLD를 보내기 전까지만 쓰는 추측. 예산 부족이 REJECTED · MANUAL_REVIEW로 와도 '보류'로 보인다.
 * 규격 8번(프론트는 상태를 추론하지 않음)에 어긋나므로, 서버 · 에이전트가 ON_HOLD를 보내기 시작하면 이 함수와 호출부를 지운다.
 */
export function isLegacyBudgetHold(p: StatusContext): boolean {
  return p.reason_code === 'BUDGET_INSUFFICIENT' && (p.status === 'REJECTED' || p.status === 'MANUAL_REVIEW')
}
/** 보류 화면을 써야 하는지: 서버의 ON_HOLD, 또는 위 임시 추측. */
export function isOnHold(p: StatusContext): boolean {
  return p.status === 'ON_HOLD' || isLegacyBudgetHold(p)
}

/** 규격 7: 여러 단계 결재면 "1/2단계 승인 대기". 단계 정보가 없거나 1단계뿐이면 null. */
export function stepText(p: StatusContext): string | null {
  const total = p.total_steps ?? 0
  const cur = p.current_step ?? null
  return total > 1 && cur ? `${cur}/${total}단계` : null
}

/** 규격 6: 완료는 사유별로 문구를 나눈다. 회수 점검을 '권한 회수 완료'로 쓰지 않는다. */
export const DONE_TEXT: Record<string, { badge: string; headline: string }> = {
  VERIFIED:           { badge: '부여 완료',      headline: '권한 부여 완료' },
  ALREADY_HAS_ACCESS: { badge: '이미 보유',      headline: '조회 결과 필요한 권한을 이미 보유하고 있어요' },
  RAG_GUIDANCE:       { badge: '안내 완료',      headline: '안내 완료' },
  SCAN_COMPLETED:     { badge: '점검 완료',      headline: '회수 후보 점검 완료' },
  NO_NEW_CANDIDATES:  { badge: '신규 후보 없음', headline: '신규 회수 후보 없음' },
}
/** 사유 코드가 없던 기존 완료: 승인 결정이 있으면 부여 완료, 없으면 이미 보유. */
export function doneKind(p: StatusContext): string {
  if (p.reason_code && DONE_TEXT[p.reason_code]) return p.reason_code
  if (p.result_type === 'GUIDANCE') return 'RAG_GUIDANCE'
  if (p.result_type === 'ACCESS_VERIFIED') return 'VERIFIED'
  return p.decided_at ? 'VERIFIED' : 'ALREADY_HAS_ACCESS'
}

/** 이미 필요한 권한이 있어 바꾼 것 없이 끝난 요청(v2는 DONE · GUIDANCE · ALREADY_HAS_ACCESS로 온다). '안내 완료'와 구분한다. */
export function isAlreadyHas(p: StatusContext): boolean {
  return p.status === 'DONE' && p.reason_code === 'ALREADY_HAS_ACCESS'
}

export function statusOf(p: StatusContext) {
  if (isAlreadyHas(p)) return { ...STATUS.DONE, label: DONE_TEXT.ALREADY_HAS_ACCESS.badge }
  if (isGuidanceComplete(p)) return { label: '안내 완료', tone: 'ok' as const, terminal: true }
  if (isLegacyBudgetHold(p)) return { label: '보류', tone: 'review' as const, terminal: true }
  if (p.status === 'DONE') return { ...STATUS.DONE, label: DONE_TEXT[doneKind(p)].badge }
  const step = p.status === 'WAITING_APPROVAL' ? stepText(p) : null
  if (step) return { ...STATUS.WAITING_APPROVAL, label: `${step} 승인 대기` }
  return STATUS[p.status]
}

/**
 * 홈 · 내 요청의 묶음. 요청자 입장에서 나눈다.
 * 안내 완료와 (임시) 예산 보류 추측은 '끝난 요청', 보류(ON_HOLD) · 담당자 검토는 '확인 대기'.
 */
export type StatusGroup = 'progress'|'waiting'|'finished'
export function groupOf(p: StatusContext): StatusGroup {
  if (isGuidanceComplete(p) || isLegacyBudgetHold(p)) return 'finished'
  const { status } = p
  if (status === 'WAITING_APPROVAL' || status === 'ON_HOLD' || status === 'MANUAL_REVIEW') return 'waiting'
  return STATUS[status].terminal ? 'finished' : 'progress'
}

/**
 * 화면이 계속 다시 불러와야 하는지. 담당자 검토는 서버에선 끝난 상태지만
 * 담당자가 처리하면 결과가 바뀌므로, 열려 있는 화면은 계속 확인한다(탭이 가려지면 쉰다).
 */
export function needsRefresh(p: StatusContext) {
  const { status } = p
  return !STATUS[status].terminal || status === 'MANUAL_REVIEW'
}

export function isTerminal(status: Status) {
  return STATUS[status].terminal
}
