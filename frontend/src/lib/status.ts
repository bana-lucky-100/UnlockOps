import type { Status } from '../api'

/** 상태 8개의 화면 표기. 색: 진행 = 남보라, 승인 대기 = 주황, 담당자 검토 = 청록(+사람 아이콘), 완료 = 초록, 거절 · 실패 = 빨강. */
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

/** 홈의 상태별 묶음. 끝난 상태는 다시 바뀌지 않는다(명세: 상태 전이도). */
export type StatusGroup = 'progress'|'waiting'|'finished'
export function groupOf(status: Status): StatusGroup {
  if (status === 'WAITING_APPROVAL') return 'waiting'
  return STATUS[status].terminal ? 'finished' : 'progress'
}

export function isTerminal(status: Status) {
  return STATUS[status].terminal
}
