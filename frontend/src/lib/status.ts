import type { Problem, Status } from '../api'

/** 상태 8개의 화면 표기. 색: 진행 = 남보라, 확인 대기(승인 대기 · 담당자 검토) = 주황, 완료 = 초록, 거절 · 실패 = 빨강. 담당자 검토는 사람 아이콘을 붙인다. */
export const STATUS: Record<Status, { label: string; tone: 'run'|'warn'|'review'|'ok'|'bad'; terminal: boolean }> = {
  RECEIVED:         { label: '접수',        tone: 'run',  terminal: false },
  DIAGNOSING:       { label: '진단 중',     tone: 'run',  terminal: false },
  WAITING_APPROVAL: { label: '승인 대기',   tone: 'warn', terminal: false },
  EXECUTING:        { label: '부여 중',     tone: 'run',  terminal: false },
  DONE:             { label: '완료',        tone: 'ok',   terminal: true },
  REJECTED:         { label: '거절',        tone: 'bad',  terminal: true },
  MANUAL_REVIEW:    { label: '담당자 검토', tone: 'review', terminal: true },
  FAILED:           { label: '실패',        tone: 'bad',  terminal: true },
}

type StatusContext = Pick<Problem, 'status' | 'result_type'>

/** 완료 여부는 status, 완료 대상은 result_type으로 판단한다. */
export function isGuidanceComplete(p: StatusContext): boolean {
  return p.status === 'DONE' && p.result_type === 'GUIDANCE'
}

export function statusOf(p: StatusContext) {
  return isGuidanceComplete(p) ? { label: '안내 완료', tone: 'ok' as const, terminal: true } : STATUS[p.status]
}

/**
 * 홈 · 내 요청의 묶음. 요청자 입장에서 나눈다.
 * DONE은 '끝난 요청', MANUAL_REVIEW는 '확인 대기'에 넣는다.
 */
export type StatusGroup = 'progress'|'waiting'|'finished'
export function groupOf(p: StatusContext): StatusGroup {
  const { status } = p
  if (status === 'WAITING_APPROVAL' || status === 'MANUAL_REVIEW') return 'waiting'
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
