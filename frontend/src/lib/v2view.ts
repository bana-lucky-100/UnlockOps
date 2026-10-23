import type { Platform, Problem } from '../api'
import { shortArticle } from './policyRef.ts'
import type { AccessReport, AccessSummary } from '../phase2/api'
import { personaName } from './persona.ts'
import { SAAS_MONTHLY_COST, type CostImpact } from './costImpact.ts'

/** v2(Phase 2) 응답을 화면용 Problem으로 옮기는 순수 함수. 네트워크 · 세션에 기대지 않아 테스트에서 바로 부른다. */
const COST_KIND = { SEAT_MONTHLY: 'NEW_COST', USAGE_ESTIMATE: 'NEW_COST', NO_ADDITIONAL_COST: 'NO_COST' } as const
const COST_BASIS_TEXT: Record<string, string> = { SEAT_MONTHLY: '좌석 월 요금', USAGE_ESTIMATE: '사용량 기준 월 예상', NO_ADDITIONAL_COST: '추가 비용 없음' }
const COST_KEY: Record<string, string> = { TABLEAU_CLOUD: 'TABLEAU' }

/**
 * [임시] 부서 잔여 예산 전후 값. v2 보고서에 예산 필드가 없어서, 서버가 판정 때 쓴 메시지
 * "예상 예산 영향은 500.00 → 380.00 USD입니다"에서 읽는다(AccessPlanningService). 서버가 budget 필드를 주면 이 함수를 지운다.
 */
export function budgetFromMessage(message: string | null | undefined, currency: string): { before: number; after: number } | null {
  const m = String(message ?? '').match(/예상 예산 영향은\s*(-?[\d.]+)\s*→\s*(-?[\d.]+)\s*([A-Z]{3})/)
  if (!m || m[3] !== currency) return null
  const before = Number(m[1]), after = Number(m[2])
  return Number.isFinite(before) && Number.isFinite(after) ? { before, after } : null
}

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
    requester_name: personaName(x.requester_name),
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
    approvers: r?.approvers.map(a => ({ ...a, name: personaName(a.name) })),
    resource_name: r?.resource_name ?? null,
    created_at: x.created_at,
    updated_at: history.at(-1)?.created_at ?? last?.acted_at ?? x.created_at,
    evidence: (r?.policy_evidence ?? []).map(e => ({ doc_id: e.doc_id, article: e.article, version: e.version, text: e.text })),
    decision_reason: last?.reason ?? null,
    decided_at: last?.acted_at ?? null,
    decided_by: last ? personaName(r?.approvers.find(a => a.id === last.approver_id)?.name ?? null) : null,
    plan: plan ? { resource_key: r?.resource_name ?? plan.resource_id, requested_role: r?.entitlement_code ?? '', resource_id: plan.resource_id } : null,
    monthly_cost: plan ? { amount: plan.monthly_amount, currency: plan.currency } : null,
    // 부서 잔여 예산은 v2 보고서에 없어서 비워 둔다(카드는 월 비용만 보여 준다).
    cost_impact: plan && Number.isFinite(amount) ? costOf(x.platform, plan, w.message, r?.policy_evidence ?? []) : null,
    events: history.map(h => ({ kind: h.kind, payload: {}, created_at: h.created_at })),
  }
}


function costOf(platform: string, plan: NonNullable<AccessReport['plan']>, message: string, evidence: AccessReport['policy_evidence']): CostImpact {
  const budget = budgetFromMessage(message, plan.currency)
  const what = SAAS_MONTHLY_COST[COST_KEY[platform] ?? platform]?.basis
  const ev = (evidence ?? [])[0]
  return {
    kind: COST_KIND[plan.cost_basis], monthly_cost: Number(plan.monthly_amount),
    budget_before: budget?.before ?? null, budget_after: budget?.after ?? null,
    // 금액 · 기준 · 가격표 버전은 서버 계획(plan) 값만 쓴다. 자원 설명(what)만 화면 표에서 붙인다.
    basis: [what, COST_BASIS_TEXT[plan.cost_basis], `가격표 rev ${plan.pricing_revision}`, plan.currency !== 'USD' ? plan.currency : null].filter(Boolean).join(' · ') + ' (가상 회사 가정 금액)',
    // 서버가 판정에 쓴 규정 문서 · 조항을 그대로 적는다(조항 내용을 화면에서 추측해 붙이지 않는다).
    // 실제 article은 'POL-09 | SNOWFLAKE | v1.0 | 제2조(…)'처럼 원문 ID를 품는다. ID가 없는 형식이면 문서 ID를 앞에 붙인다.
    rule: ev ? `판정에 쓴 규정 ${ev.article.includes('|') ? shortArticle(ev.article) : `${ev.doc_id} ${ev.article}`}` : null,
  }
}

/** 현재 단계의 지정 승인자가 me인지. #29 phase2/presentation.ts의 canDecide와 같은 기준이다. */
export function isMyStep(p: Problem, me: string | null | undefined): boolean {
  const waiting = (p.approval_steps ?? []).filter(s => s.status === 'WAITING')
  return !!me && p.status === 'WAITING_APPROVAL' && !!p.plan_hash && (p.plan_version ?? 0) > 0
    && waiting.length === 1 && waiting[0].step === p.current_step && waiting[0].approver_id === me
}
