import type { Status } from '../api'

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

/**
 * 홈 · 내 요청의 묶음. 요청자 입장에서 나눈다.
 * MANUAL_REVIEW는 서버에서는 끝난 상태지만 요청자에게는 아직 사람이 확인 중이라 '확인 대기'에 넣는다(표시만, 상태값은 그대로).
 */
export type StatusGroup = 'progress'|'waiting'|'finished'
export function groupOf(status: Status): StatusGroup {
  if (status === 'WAITING_APPROVAL' || status === 'MANUAL_REVIEW') return 'waiting'
  return STATUS[status].terminal ? 'finished' : 'progress'
}

/**
 * 화면이 계속 다시 불러와야 하는지. 담당자 검토는 서버에선 끝난 상태지만
 * 담당자가 처리하면 결과가 바뀌므로, 열려 있는 화면은 계속 확인한다(탭이 가려지면 쉰다).
 */
export function needsRefresh(status: Status) {
  return !STATUS[status].terminal || status === 'MANUAL_REVIEW'
}

export function isTerminal(status: Status) {
  return STATUS[status].terminal
}
