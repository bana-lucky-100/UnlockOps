import type { Problem, Status } from '../api'

/**
 * 요청자 화면에 무엇을 보여줄지 정하는 규칙을 한곳에 둔다 (명세: 화면별 명세 · 판단 근거는 승인자에게만).
 * - REJECTED · MANUAL_REVIEW에서는 diagnosis를 받더라도 보여주지 않고 고정 문구를 쓴다.
 * - 거절 이유는 승인자가 남긴 메모(decision_reason)가 있을 때만 보여준다.
 */

export type StageKind = 'done' | 'cur' | 'todo' | 'warn' | 'fail'
export interface Stage { label: string; sub: string; kind: StageKind }

const LABELS = ['요청 접수', 'AI 진단', '승인', '권한 부여', '반영 확인'] as const

function stages(kinds: StageKind[], subs: string[]): Stage[] {
  return LABELS.map((label, i) => ({ label, kind: kinds[i], sub: subs[i] ?? '' }))
}

/** 승인자가 결정해서 거절된 것인지(사람) 규정 · 예산으로 바로 거절된 것인지(AI). */
export function rejectedByApprover(p: Problem) {
  return p.status === 'REJECTED' && !!p.decided_at
}

export function stagesOf(p: Problem): Stage[] {
  const s: Status = p.status
  switch (s) {
    case 'RECEIVED': return stages(['cur', 'todo', 'todo', 'todo', 'todo'], ['접수됨', '', '부서 승인자', '자동 부여', '다시 조회해 확인'])
    case 'DIAGNOSING': return stages(['done', 'cur', 'todo', 'todo', 'todo'], ['', '확인 중', '부서 승인자', '자동 부여', '다시 조회해 확인'])
    case 'WAITING_APPROVAL': return stages(['done', 'done', 'cur', 'todo', 'todo'], ['', '원인 찾음', '승인자 검토 중', '자동 부여', '다시 조회해 확인'])
    case 'EXECUTING': return stages(['done', 'done', 'done', 'cur', 'todo'], ['', '원인 찾음', '승인됨', '부여 중', '다시 조회해 확인'])
    case 'DONE': return p.decided_at
      ? stages(['done', 'done', 'done', 'done', 'done'], ['', '원인 찾음', '승인됨', '부여 완료', '다시 조회 ✓'])
      : stages(['done', 'done', 'done', 'done', 'done'], ['', '이미 권한 있음', '필요 없음', '필요 없음', '다시 조회 ✓'])
    case 'REJECTED': return rejectedByApprover(p)
      ? stages(['done', 'done', 'fail', 'todo', 'todo'], ['', '원인 찾음', '승인자 거절', '', ''])
      : stages(['done', 'fail', 'todo', 'todo', 'todo'], ['', '거절', '', '', ''])
    case 'MANUAL_REVIEW': return stages(['done', 'warn', 'todo', 'todo', 'todo'], ['', '담당자 확인 필요', '', '', ''])
    case 'FAILED': return stages(['done', 'done', 'done', 'fail', 'todo'], ['', '원인 찾음', '승인됨', '부여 실패', '반영 안 됨'])
  }
}

export function summaryOf(p: Problem): string {
  switch (p.status) {
    case 'RECEIVED': return '요청을 받았어요. 곧 AI가 확인을 시작해요.'
    case 'DIAGNOSING': return 'AI가 소속과 현재 권한을 확인하고 있어요. 이 화면을 닫아도 계속 진행돼요.'
    case 'WAITING_APPROVAL': return 'AI가 빠진 권한을 찾았어요. 승인되면 바로 부여돼요.'
    case 'EXECUTING': return '승인됐어요. 권한을 넣고 다시 조회해 확인하고 있어요.'
    case 'DONE': return p.decided_at ? '권한이 열렸어요. 다시 조회해 반영을 확인했어요.' : '이미 필요한 권한이 있어요. 다시 조회해 확인했어요.'
    case 'REJECTED': return rejectedByApprover(p) ? '승인자가 이번 요청을 거절했어요.' : '이 권한은 자동으로 드릴 수 없어 거절됐어요. 다음에 할 일을 확인해 주세요.'
    case 'MANUAL_REVIEW': return '요청 내용만으로는 필요한 권한을 정하기 어려워 담당자가 확인하고 있어요.'
    case 'FAILED': return '승인됐지만 권한을 넣지 못했어요. 운영 담당자가 확인하고 있어요.'
  }
}

/** AI 말풍선. 거절 · 담당자 검토에서는 판단 근거가 섞인 diagnosis 대신 고정 문구. */
export function aiMessageOf(p: Problem): string | null {
  if (p.status === 'REJECTED') return rejectedByApprover(p)
    ? '원인을 찾아 승인자에게 올렸어요.'
    : '확인해 보니 이 권한은 자동으로 드릴 수 없어요.'
  if (p.status === 'MANUAL_REVIEW') return '요청 내용만으로는 어떤 권한이 필요한지 정하기 어려워 담당자에게 넘겼어요.'
  return p.diagnosis?.trim() || null
}

/** 제안 문구는 AI 문장이 아니라 계획(플랫폼 · 역할)으로 만든다 (명세: diagnosis와 proposal 분리 대신). */
export function proposalOf(p: Problem, platformLabel: string): string | null {
  if (!p.requested_role) return null
  if (!['WAITING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED'].includes(p.status)) return null
  if (p.status === 'DONE' && !p.decided_at) return null
  return `${platformLabel}에서 ${p.requested_role} 권한을 주면 해결돼요.`
}

export interface Notice { tone: 'bad' | 'warn'; title: string; memo: string | null; next: string }

/** 오른쪽 안내 카드. 판단 근거(규정 번호 · 판단 주체)는 넣지 않는다. */
export function noticeOf(p: Problem): Notice | null {
  if (p.status === 'REJECTED') {
    const memo = p.decision_reason?.trim() || null
    return rejectedByApprover(p)
      ? { tone: 'bad', title: '승인자가 거절했어요', memo, next: '메모를 확인하고, 필요하면 내용을 보완해 다시 요청하세요' }
      : { tone: 'bad', title: '거절됐어요', memo: null, next: '업무에 꼭 필요하면 부서 승인자에게 문의하세요' }
  }
  if (p.status === 'MANUAL_REVIEW') return { tone: 'warn', title: '담당자가 확인하고 있어요', memo: null, next: '확인이 끝나면 이 화면과 홈에서 알려드릴게요. 따로 할 일은 없어요' }
  if (p.status === 'FAILED') return { tone: 'bad', title: '부여 실패 · 운영 담당자 확인 중', memo: null, next: '처음 시도를 포함해 총 3번 시도했어요. 처리되면 이 화면과 홈에서 알려드릴게요. 다른 플랫폼 요청에는 영향이 없어요' }
  return null
}
