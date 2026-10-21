import type { Problem, Status } from '../api'
import { isGuidanceComplete } from './status.ts'

/**
 * 요청자 화면에 무엇을 보여줄지 정하는 규칙을 한곳에 둔다 (명세: 화면별 명세 · 판단 근거는 승인자에게만).
 * - REJECTED · 실제 MANUAL_REVIEW에서는 고정 문구를 쓰되, 안내 성공은 API의 진단을 보여준다.
 * - 거절 이유는 승인자가 남긴 메모(decision_reason)가 있을 때만 보여준다.
 */

export type StageKind = 'done' | 'cur' | 'todo' | 'review' | 'fail'
export interface Stage { label: string; sub: string; kind: StageKind }

const LABELS = ['요청 접수', 'AI 진단', '승인', '권한 부여', '반영 확인'] as const

function stages(kinds: StageKind[], subs: string[]): Stage[] {
  return LABELS.map((label, i) => ({ label, kind: kinds[i], sub: subs[i] ?? '' }))
}

/** 승인자가 결정해서 거절된 것인지(사람) 규정 · 예산으로 바로 거절된 것인지(AI). */
export function rejectedByApprover(p: Problem) {
  return p.status === 'REJECTED' && !!p.decided_at
}

/** 대상 이름이 없어서 담당자 검토로 넘어간 경우. 요청자가 이름을 넣어 다시 보내면 풀린다. */
export function needsName(p: Problem) {
  return p.status === 'MANUAL_REVIEW' && p.reason_code === 'RESOURCE_NOT_UNIQUE'
}

export function stagesOf(p: Problem): Stage[] {
  if (isGuidanceComplete(p)) return [
    { label: '요청 접수', sub: '', kind: 'done' },
    { label: 'AI 진단', sub: '분석 완료', kind: 'done' },
    { label: '안내 제공', sub: '안내 완료', kind: 'done' },
  ]
  const s: Status = p.status
  switch (s) {
    case 'RECEIVED': return stages(['cur', 'todo', 'todo', 'todo', 'todo'], ['접수됨', '', '승인자 검토', '자동 부여', '다시 조회해 확인'])
    case 'DIAGNOSING': return stages(['done', 'cur', 'todo', 'todo', 'todo'], ['', '확인 중', '승인자 검토', '자동 부여', '다시 조회해 확인'])
    case 'WAITING_APPROVAL': return stages(['done', 'done', 'cur', 'todo', 'todo'], ['', '원인 찾음', '승인자 검토 중', '자동 부여', '다시 조회해 확인'])
    case 'EXECUTING': return stages(['done', 'done', 'done', 'cur', 'todo'], ['', '원인 찾음', '승인됨', '부여 중', '다시 조회해 확인'])
    case 'DONE': return p.decided_at
      ? stages(['done', 'done', 'done', 'done', 'done'], ['', '원인 찾음', '승인됨', '부여 완료', '다시 조회 ✓'])
      : stages(['done', 'done', 'done', 'done', 'done'], ['', '이미 권한 있음', '필요 없음', '필요 없음', '다시 조회 ✓'])
    case 'REJECTED': return rejectedByApprover(p)
      ? stages(['done', 'done', 'fail', 'todo', 'todo'], ['', '원인 찾음', '승인자 거절', '', ''])
      : stages(['done', 'fail', 'todo', 'todo', 'todo'], ['', '거절', '', '', ''])
    case 'MANUAL_REVIEW': return stages(['done', 'review', 'todo', 'todo', 'todo'], ['', needsName(p) ? '대상 이름 필요' : '담당자가 확인 중', '', '', ''])
    case 'FAILED': return stages(['done', 'done', 'done', 'fail', 'todo'], ['', '원인 찾음', '승인됨', '부여 실패', '반영 안 됨'])
  }
}

export function summaryOf(p: Problem): string {
  if (isGuidanceComplete(p)) return '안내가 완료됐어요.'
  switch (p.status) {
    case 'RECEIVED': return '요청을 받았어요. 곧 AI가 확인을 시작해요.'
    case 'DIAGNOSING': return 'AI가 소속과 현재 권한을 확인하고 있어요. 이 화면을 닫아도 계속 진행돼요.'
    case 'WAITING_APPROVAL': return 'AI가 빠진 권한을 찾았어요. 승인되면 바로 부여돼요.'
    case 'EXECUTING': return '승인됐어요. 권한을 넣고 다시 조회해 확인하고 있어요.'
    case 'DONE': return p.decided_at ? '권한이 열렸어요. 다시 조회해 반영을 확인했어요.' : '이미 필요한 권한이 있어요. 다시 조회해 확인했어요.'
    case 'REJECTED': return rejectedByApprover(p) ? '승인자가 이번 요청을 거절했어요.' : '이 권한은 자동으로 드릴 수 없어 거절됐어요. 다음에 할 일을 확인해 주세요.'
    case 'MANUAL_REVIEW': return needsName(p)
      ? '어떤 저장소 · 프로젝트인지 알 수 없어 확인이 멈췄어요. 이름을 넣어 다시 보내 주세요.'
      : '요청 내용만으로는 필요한 권한을 정하기 어려워 담당자가 확인하고 있어요.'
    case 'FAILED': return '승인됐지만 권한을 넣지 못했어요. 운영 담당자가 확인하고 있어요.'
  }
}

/**
 * AI 말풍선은 서버가 준 진단 문장(diagnosis)만 보여준다.
 * 안내 성공을 제외한 거절 · 담당자 검토에서는 판단 근거가 섞여 있어 숨긴다.
 * 그 상태의 안내는 오른쪽 안내 카드가 맡는다.
 */
export function aiMessageOf(p: Problem): string | null {
  if (p.status === 'REJECTED' || (p.status === 'MANUAL_REVIEW' && !isGuidanceComplete(p))) return null
  return p.diagnosis?.trim() || null
}

/** 안내 성공은 API 본문을 사용하고, 권한 부여 제안은 계획(플랫폼 · 역할)으로 만든다. */
export function proposalOf(p: Problem, platformLabel: string): string | null {
  if (isGuidanceComplete(p)) return p.proposal!.trim()
  if (!p.requested_role) return null
  if (!['WAITING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED'].includes(p.status)) return null
  if (p.status === 'DONE' && !p.decided_at) return null
  return `${platformLabel}에서 ${p.requested_role} 권한을 주면 해결돼요.`
}

/** nextLabel: 요청자가 직접 할 일이 있으면 '다음에 할 일', 기다리기만 하면 되는 경우는 '안내'. */
export interface Notice { tone: 'bad' | 'review'; title: string; memo: string | null; nextLabel: string; next: string; resend?: boolean }

/** 오른쪽 안내 카드. 판단 근거(규정 번호 · 판단 주체)는 넣지 않는다. */
export function noticeOf(p: Problem): Notice | null {
  if (isGuidanceComplete(p)) return null
  if (p.status === 'REJECTED') {
    const memo = p.decision_reason?.trim() || null
    return rejectedByApprover(p)
      ? { tone: 'bad', title: '승인자가 거절했어요', memo, nextLabel: '다음에 할 일', next: '메모를 확인하고, 필요하면 내용을 보완해 다시 요청하세요' }
      : { tone: 'bad', title: '거절됐어요', memo: null, nextLabel: '다음에 할 일', next: '업무에 꼭 필요하면 승인자에게 문의하세요' }
  }
  // 이름이 없어서 대상을 정하지 못한 경우는 요청자가 이름을 넣어 다시 보내면 바로 풀린다.
  if (needsName(p)) return { tone: 'review', title: '어떤 대상인지 알려 주세요', memo: null, nextLabel: '다음에 할 일', next: '저장소 · 프로젝트 · 채널 · 페이지 이름을 넣어 다시 보내 주세요. AI가 바로 다시 확인해요', resend: true }
  if (p.status === 'MANUAL_REVIEW') return { tone: 'review', title: '담당자가 확인하고 있어요', memo: null, nextLabel: '안내', next: '확인이 끝나면 이 화면과 홈에서 알려드릴게요' }
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

/** 기존 서버가 안내 성공에 붙인 마지막 분석 이벤트의 검토 문구도 완료로 표시한다. */
function guidanceEventIndex(p: Problem): number {
  return isGuidanceComplete(p) ? (p.events ?? []).map(e => e.kind).lastIndexOf('ANALYZED') : -1
}

export function requesterEventsOf(p: Problem): { at: string; text: string }[] {
  const guidanceIndex = guidanceEventIndex(p)
  return (p.events ?? []).map((e, i) => ({
    at: e.created_at,
    text: i === guidanceIndex ? '안내가 완료됐어요' : typeof e.payload?.message === 'string' ? e.payload.message : '',
  })).filter(e => e.text)
}

/** 승인자는 원본 이벤트를 받는다. 요청자 화면과 같은 말투의 짧은 문장으로 바꾼다. */
export function approverEventsOf(p: Problem): { at: string; text: string }[] {
  const STATUS_TEXT: Partial<Record<Status, string>> = {
    WAITING_APPROVAL: 'AI가 원인을 찾아 승인을 요청했어요',
    MANUAL_REVIEW: '담당자 검토가 필요하다고 판단했어요',
    REJECTED: '규정상 자동으로 줄 수 없어 거절됐어요',
    DONE: '다시 조회해 반영을 확인했어요',
    FAILED: '권한을 넣지 못했어요',
  }
  const out: { at: string; text: string }[] = []
  let prev = ''
  const guidanceIndex = guidanceEventIndex(p)
  for (const [i, e] of (p.events ?? []).entries()) {
    const pl = (e.payload ?? {}) as Record<string, unknown>
    const result = pl.result as Record<string, unknown> | undefined
    const text = i === guidanceIndex ? '안내가 완료됐어요'
      : e.kind === 'PROGRESS' ? (pl.job_type === 'EXECUTE' ? '권한을 넣고 있어요' : 'AI가 요청을 분석하고 있어요')
      : e.kind === 'HUMAN_DECISION' ? (pl.approved ? '승인했어요' : '거절했어요')
      : (e.kind === 'ANALYZED' || e.kind === 'EXECUTED') && result ? STATUS_TEXT[result.status as Status] ?? ''
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
  if (p.status === 'MANUAL_REVIEW') return { tone: 'review', title: '담당자 확인이 필요한 요청이에요', body: 'AI가 자동으로 판단하지 못했어요. 왼쪽의 진단과 판단 근거를 확인해 주세요. 이 화면에서 바로 처리하는 기능은 아직 없어요.' }
  if (p.status === 'FAILED') return { tone: 'bad', title: '권한 부여에 실패했어요', body: '승인 뒤 처음 시도를 포함해 총 3번 시도했지만 권한을 넣지 못했어요. 대상 플랫폼의 상태를 확인해 주세요.' }
  if (p.status === 'REJECTED' && !p.decided_at) return { tone: 'bad', title: '규정상 자동으로 거절된 요청이에요', body: '거절 이유는 왼쪽 판단 근거에서 확인할 수 있어요. 요청자에게는 이유 대신 승인자에게 문의하라고 안내돼요.' }
  return null
}

export function approverSummaryOf(p: Problem): string {
  if (isGuidanceComplete(p)) return summaryOf(p)
  if (needsName(p)) return '요청자가 대상 이름을 적지 않아 AI가 대상을 정하지 못했어요.'
  if (p.status === 'MANUAL_REVIEW') return 'AI가 자동으로 판단하지 못해 담당자 확인이 필요해요.'
  if (p.status === 'REJECTED' && !p.decided_at) return '규정에 맞지 않아 AI가 바로 거절했어요.'
  return summaryOf(p)
}
