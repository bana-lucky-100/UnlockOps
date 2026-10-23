import type { Problem } from '../api'
import type { CostImpact } from './costImpact.ts'

/**
 * 승인자 화면 맨 위 '한 장 요약'(시안 A). 결론 한 줄 → 숫자 3개 → 왜 괜찮은지 → 승인 순서.
 * 판정은 서버 규칙이 이미 했고, 여기서는 서버가 준 값(상태 · 사유 · 계획 · 근거 · 단계)만 쉬운 말로 다시 묶는다.
 * 값이 없는 줄은 만들지 않는다(추측 금지).
 */
export interface SummaryCheck { text: string; detail?: string; ref?: { id: string; label: string } }
export interface SummaryStep { label: string; who: string; state: 'done' | 'on' | 'wait' | 'bad' }
export interface DecisionSummary {
  tone: 'ok' | 'review' | 'done'
  badge: string
  headline: string
  sub: string
  numbers: { big: string; label: string }[]
  checks: SummaryCheck[]
  steps: SummaryStep[]
}

/** 받침이 있으면 '을', 없으면 '를'. 한글이 아니면 '을(를)'. */
export function objectJosa(word: string): string {
  const c = word.trim().slice(-1).charCodeAt(0)
  if (c < 0xac00 || c > 0xd7a3) return '을(를)'
  return (c - 0xac00) % 28 ? '을' : '를'
}

const usd = (n: number) => `$${Number.isInteger(Math.abs(n)) ? Math.abs(n) : Math.abs(n).toFixed(2)}`
const FORBIDDEN = new Set(['admin', 'owner', 'project admin', 'full access'])
const STEP_STATE: Record<string, SummaryStep['state']> = { APPROVED: 'done', WAITING: 'on', PENDING: 'wait', REJECTED: 'bad', ON_HOLD: 'bad', SKIPPED: 'wait' }
const STEP_WORD: Record<string, string> = { APPROVED: '완료', WAITING: '검토 중', PENDING: '대기', REJECTED: '반려', ON_HOLD: '보류', SKIPPED: '건너뜀' }

export function decisionSummaryOf(p: Problem, title: string, cost: CostImpact | null, meId?: string | null): DecisionSummary | null {
  const ok = p.status === 'WAITING_APPROVAL'
  const hold = p.status === 'ON_HOLD'
  if (!ok && !hold) return null
  const ev = (p.evidence ?? []).find(e => typeof e.doc_id === 'string')
  // 원문 버튼은 서버가 준 규정 문서로 내려간다. 조항 번호를 화면에서 지어내지 않도록 이름은 '규정 원문'으로 둔다.
  const ref = (_topic: string) => (ev?.doc_id ? { id: String(ev.doc_id), label: '규정 원문' } : undefined)
  // 승인자는 대리 · 재지정으로 바뀔 수 있고 이름을 앞세우면 압박처럼 읽혀서, 사람 대신 단계 이름(1차 · 2차 · 최종)으로 보인다.
  // 지금 보는 사람의 단계만 '나'를 붙인다.
  const raw = p.approval_steps ?? []
  const lastStep = raw.length ? Math.max(...raw.map(s => s.step)) : 0
  const stepName = (n: number) => (n === lastStep ? (raw.length > 1 ? '최종 승인' : '승인') : `${n}차 승인`)
  const steps: SummaryStep[] = raw.map(s => ({
    label: STEP_WORD[s.status] ?? s.status,
    who: stepName(s.step) + (meId && String(s.approver_id) === String(meId) ? ' · 나' : ''),
    state: STEP_STATE[s.status] ?? 'wait',
  }))
  if (steps.length) steps.push({ label: '부여 · 확인', who: '자동', state: 'wait' })

  const numbers: DecisionSummary['numbers'] = []
  if (cost) {
    numbers.push(cost.kind === 'NO_COST' ? { big: '추가 비용 없음', label: '예상 비용' } : { big: `월 ${usd(cost.monthly_cost)}`, label: '예상 비용' })
    if (cost.budget_before !== null && cost.budget_after !== null) {
      numbers.push({ big: `${usd(cost.budget_before)} → ${usd(cost.budget_after)}`, label: '부서 잔여 예산' })
      if (cost.kind !== 'NO_COST' && cost.budget_before > 0)
        numbers.push({ big: `${Math.min(100, Math.round((cost.monthly_cost / cost.budget_before) * 100))}%`, label: '예산 사용 비율' })
    }
  }
  if (steps.length) numbers.push({ big: `${p.current_step ?? '-'}/${p.total_steps ?? steps.length - 1}단계`, label: '승인 진행' })

  const checks: SummaryCheck[] = []
  const role = String(p.requested_role ?? '').trim()
  if (role && !FORBIDDEN.has(role.toLowerCase())) checks.push({ text: '필요한 만큼만 줘요 · 관리자 권한이 아니에요', detail: `권한 항목 ${role}` })
  if (ok && cost && cost.kind !== 'NO_COST') {
    checks.push(cost.budget_after !== null
      ? { text: `부서 예산 안이에요 · 승인 뒤에도 ${usd(cost.budget_after)} 남아요`, ref: ref('POL-06 제2조') }
      : { text: '부서 예산 안이에요 · 규칙이 잔여 예산을 확인했어요', ref: ref('POL-06 제2조') })
  }
  if (ok && cost?.kind === 'NO_COST') checks.push({ text: '추가 비용이 없어 부서 예산에 영향이 없어요' })
  if (steps.length > 1) checks.push({ text: `승인 순서가 정해져 있어요 · ${raw.map(s => stepName(s.step)).join(' → ')}`, ref: ref('FLOW 제7조') })

  // 내가 이미 승인한 단계가 있고 아직 다음 단계가 남았으면, '승인해도 돼요'가 아니라 '승인했어요 · 다음은 누구'로 보여 준다.
  const mine = meId ? (p.approval_steps ?? []).find(s => String(s.approver_id) === String(meId) && s.status === 'APPROVED') : undefined
  const next = (p.approval_steps ?? []).find(s => s.status === 'WAITING')
  if (ok && mine && (!next || String(next.approver_id) !== String(meId))) {
    // 다음 승인자는 바뀔 수 있고(대리 · 재지정) 이름을 앞세우면 압박처럼 읽혀서, 사람 대신 단계만 알린다.
    return {
      tone: 'done', badge: '✓ 승인했어요',
      headline: `${title}${objectJosa(title)} ${mine.step}단계 승인했어요`,
      sub: next ? `다음 단계(${next.step}/${p.total_steps ?? steps.length - 1}) 승인을 기다리고 있어요. 모든 단계가 끝나면 바로 부여돼요` : '모든 단계가 끝나면 바로 부여돼요',
      numbers: numbers.slice(0, 3), checks: [], steps,
    }
  }
  return {
    tone: ok ? 'ok' : 'review',
    badge: ok ? '✓ 승인해도 괜찮아요' : '보류 · 조건 확인이 필요해요',
    headline: ok ? `${title}${objectJosa(title)} 승인해도 돼요` : `${title}${objectJosa(title)} 지금은 승인할 수 없어요`,
    sub: `${p.requester_name} 님 요청${p.message && hold ? ` · ${p.message}` : ''}`,
    numbers: numbers.slice(0, 3),
    checks,
    steps,
  }
}
