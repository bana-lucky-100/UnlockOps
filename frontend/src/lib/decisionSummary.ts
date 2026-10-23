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
  tone: 'ok' | 'review'
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
const STEP_WORD: Record<string, string> = { APPROVED: '승인', WAITING: '검토 중', PENDING: '대기', REJECTED: '반려', ON_HOLD: '보류', SKIPPED: '건너뜀' }

export function decisionSummaryOf(p: Problem, title: string, cost: CostImpact | null): DecisionSummary | null {
  const ok = p.status === 'WAITING_APPROVAL'
  const hold = p.status === 'ON_HOLD'
  if (!ok && !hold) return null
  const ev = (p.evidence ?? []).find(e => typeof e.doc_id === 'string')
  const ref = (label: string) => (ev?.doc_id ? { id: String(ev.doc_id), label } : undefined)
  const names = new Map((p.approvers ?? []).map(a => [a.id, a.name]))
  const steps: SummaryStep[] = (p.approval_steps ?? []).map(s => ({
    label: `${s.step}단계 · ${STEP_WORD[s.status] ?? s.status}`,
    who: names.get(String(s.approver_id)) ?? '지정 승인자',
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
  if (steps.length > 1) checks.push({ text: `승인 순서가 정해져 있어요 · ${steps.slice(0, -1).map(s => s.who).join(' → ')}`, ref: ref('FLOW 제7조') })

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
