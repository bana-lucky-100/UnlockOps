import type { Problem } from '../api'
import { MOCK } from './mock.ts'

/**
 * 판단안의 비용 영향. 계약 초안: Problem.cost_impact (에이전트 3-2 · 출력 형식 cost_impact).
 * - NEW_COST: 새 유료 좌석 · 사용량이 늘어 부서 예산에서 월 비용을 차감한다.
 * - NO_COST: 이미 계정이 있는 직원의 권한 변경. 예산에 영향이 없다.
 * 금액 단위는 USD, 월 기준. 금액은 가상 회사 A사 기준 가정 금액이다 (요구사항 정의서 4. 데이터 요구사항).
 */
export interface CostImpact {
  kind: 'NEW_COST' | 'NO_COST'
  monthly_cost: number
  budget_before: number | null
  budget_after: number | null
  basis?: string | null
  /** 비용을 판단한 규정(예: POL-06 제2조 · 예상 비용 ≤ 부서 잔여 예산). */
  rule?: string | null
}

/** SaaS별 월 예상 비용 (팀 확정표, 가정 금액). 플랫폼이 10개로 늘면 이 표를 그대로 쓴다. */
export const SAAS_MONTHLY_COST: Record<string, { label: string; basis: string; usd: number }> = {
  SNOWFLAKE:  { label: 'Snowflake', basis: '분석용 웨어하우스 월 사용', usd: 120 },
  DATABRICKS: { label: 'Databricks', basis: '모델 학습용 연산 자원 월 사용', usd: 450 },
  SALESFORCE: { label: 'Salesforce', basis: '유료 좌석 1개', usd: 180 },
  DATADOG:    { label: 'Datadog', basis: '로그 수집 · 보관 월 사용', usd: 350 },
  TABLEAU:    { label: 'Tableau Cloud', basis: '대시보드 작성용 좌석 1개', usd: 80 },
  FIGMA:      { label: 'Figma', basis: 'Dev 좌석 1개', usd: 25 },
  COPILOT:    { label: 'GitHub Copilot', basis: '유료 좌석 1개', usd: 19 },
  JIRA:       { label: 'Jira', basis: '유료 사용자 1명', usd: 15 },
  SLACK:      { label: 'Slack', basis: '유료 멤버 1명', usd: 10 },
  NOTION:     { label: 'Notion', basis: '유료 멤버 1명', usd: 20 },
}

/** 목업: 승인 시나리오(Snowflake, 개발팀 잔여 $500)와 같은 값. */
const MOCK_IMPACT: CostImpact = {
  kind: 'NEW_COST', monthly_cost: 120, budget_before: 500, budget_after: 380,
  basis: 'Snowflake 분석용 웨어하우스 월 사용 (가정)',
}

/** 서버 값이 있으면 그대로, 없으면 목업 모드에서만 목업 값을 쓴다. 둘 다 없으면 카드를 숨긴다. */
export function costImpactOf(p: Problem): { impact: CostImpact; mock: boolean } | null {
  const raw = (p as Problem & { cost_impact?: CostImpact | null }).cost_impact
  if (raw && (raw.kind === 'NEW_COST' || raw.kind === 'NO_COST')) {
    // 계약 초안이라 숫자 필드가 빠질 수 있다. 빠진 금액은 0으로 꾸미지 않는다: 월 비용이 없으면 카드를 숨기고, 예산은 null(표시 안 함).
    const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
    const monthly = num(raw.monthly_cost)
    if (monthly === null && raw.kind === 'NEW_COST') return null
    return { impact: { ...raw, monthly_cost: monthly ?? 0, budget_before: num(raw.budget_before), budget_after: num(raw.budget_after) }, mock: false }
  }
  if (MOCK && ['WAITING_APPROVAL', 'ON_HOLD', 'EXECUTING', 'DONE', 'REJECTED', 'MANUAL_REVIEW'].includes(p.status)) {
    // 예산 부족 요청은 데이터팀(잔여 $10) 예시로 보여 준다.
    const impact = p.reason_code === 'BUDGET_INSUFFICIENT' ? { ...MOCK_IMPACT, budget_before: 10, budget_after: -110 } : MOCK_IMPACT
    return { impact, mock: true }
  }
  return null
}

export const usd = (n: number) => {
  const v = Math.abs(n)
  return `${n < 0 ? '−' : ''}$${Number.isInteger(v) ? v : v.toFixed(2)}`
}

/** 잔여 예산이 월 비용보다 적은지. 예산 부족 보류(BUDGET_INSUFFICIENT)와 같은 기준. */
export function isInsufficient(c: CostImpact) {
  return c.kind === 'NEW_COST' && c.budget_before !== null && c.budget_before < c.monthly_cost
}
