import type { Platform, Problem } from '../api'
import type { AccessReport, AccessSummary } from '../phase2/api'
import type { CostImpact } from './costImpact'

/** v2(Phase 2) 응답을 화면용 Problem으로 옮기는 순수 함수. 네트워크 · 세션에 기대지 않아 테스트에서 바로 부른다. */
const COST_KIND = { SEAT_MONTHLY: 'NEW_COST', USAGE_ESTIMATE: 'NEW_COST', NO_ADDITIONAL_COST: 'NO_COST' } as const

/** v2 응답(목록 요약 · 상세 보고서) → 화면용 Problem. 상세에만 있는 값은 목록에서 비워 둔다. */
export function fromV2(x: AccessSummary | AccessReport): Problem & { cost_impact?: CostImpact | null } {
  const w = x.workflow
  const r = 'analysis_summary' in x ? (x as AccessReport) : null
  const steps = (w.approval_steps ?? []).map(s => ({ ...s, reason: s.reason ?? null, acted_at: s.acted_at ?? null }))
  const acted = steps.filter(s => s.acted_at).sort((a, b) => String(a.acted_at).localeCompare(String(b.acted_at)))
  const last = acted.at(-1) ?? null
  const history = r?.history ?? []
  const plan = r?.plan ?? null
  const amount = plan ? Number(plan.monthly_amount) : NaN
  return {
    id: w.problem_id,
    platform: x.platform as Platform,
    contents: x.contents,
    status: w.status,
    result_type: w.result_type ?? null,
    requester_name: x.requester_name,
    employee_no: '',
    // 요청자에게는 서버 메시지, 승인자 판단안 본문은 AI 분석 요약.
    diagnosis: w.message || r?.analysis_summary || undefined,
    proposal: r?.analysis_summary ?? undefined,
    reason_code: w.reason_code ?? undefined,
    requested_role: r?.entitlement_code ?? undefined,
    plan_hash: w.plan_hash ?? undefined,
    plan_version: w.plan_version ?? null,
    verification_ok: w.verification_ok ?? null,
    task_type: 'ACCESS_REQUEST',
    message: w.message,
    current_step: w.current_step ?? null,
    total_steps: w.total_steps,
    approval_steps: steps,
    approver_id: steps.find(s => s.status === 'WAITING')?.approver_id ?? undefined,
    approvers: r?.approvers,
    resource_name: r?.resource_name ?? null,
    created_at: x.created_at,
    updated_at: history.at(-1)?.created_at ?? last?.acted_at ?? x.created_at,
    evidence: (r?.policy_evidence ?? []).map(e => ({ doc_id: e.doc_id, article: e.article, version: e.version, text: e.text })),
    decision_reason: last?.reason ?? null,
    decided_at: last?.acted_at ?? null,
    decided_by: last ? (r?.approvers.find(a => a.id === last.approver_id)?.name ?? null) : null,
    plan: plan ? { resource_key: r?.resource_name ?? plan.resource_id, requested_role: r?.entitlement_code ?? '', resource_id: plan.resource_id } : null,
    monthly_cost: plan ? { amount: plan.monthly_amount, currency: plan.currency } : null,
    // 부서 잔여 예산은 v2 보고서에 없어서 비워 둔다(카드는 월 비용만 보여 준다).
    cost_impact: plan && Number.isFinite(amount)
      ? { kind: COST_KIND[plan.cost_basis], monthly_cost: amount, budget_before: null, budget_after: null, basis: plan.currency === 'USD' ? null : plan.currency }
      : null,
    events: history.map(h => ({ kind: h.kind, payload: {}, created_at: h.created_at })),
  }
}


/** 현재 단계의 지정 승인자가 me인지. #29 phase2/presentation.ts의 canDecide와 같은 기준이다. */
export function isMyStep(p: Problem, me: string | null | undefined): boolean {
  const waiting = (p.approval_steps ?? []).filter(s => s.status === 'WAITING')
  return !!me && p.status === 'WAITING_APPROVAL' && !!p.plan_hash && (p.plan_version ?? 0) > 0
    && waiting.length === 1 && waiting[0].step === p.current_step && waiting[0].approver_id === me
}
