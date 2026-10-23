import { api as sendApi, ApiError } from '../api'
import { currentUser } from '../session'
import type {
  AccessRequestInput,
  AccessView,
  ApprovalDecisionInput,
  GrantPlanV2,
  Platform,
  PolicyEvidence,
  ReclaimCandidate,
  ReclaimRunView
} from '../contracts/phase2'
import { Submission } from './submission'
import { statuses, uuid } from './presentation'

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const owner = currentUser.value?.id
  try {
    return await sendApi<T>(path, options)
  } catch (e) {
    if (e instanceof ApiError && e.status === 401 && currentUser.value?.id === owner) currentUser.value = null
    throw e
  }
}

export interface CatalogItem {
  entitlement_id: string
  resource_id: string
  platform: Platform
  resource_name: string
  resource_key: string
  entitlement_code: string
  kind: string
}
export interface AccessSummary {
  workflow: AccessView
  contents: string
  platform: Platform
  requester_id: string
  requester_name: string
  created_at: string
}
export interface AccessReport extends AccessSummary {
  analysis_summary: string | null
  plan: GrantPlanV2 | null
  policy_evidence: PolicyEvidence[] | null
  approvers: { id: string; name: string }[]
  resource_name: string | null
  entitlement_code: string | null
  history: { id: number; kind: string; created_at: string }[]
}
export interface Scope {
  id: string
  scope_key: string
  platforms: Platform[]
  enabled: boolean
}
export interface Notification {
  id: string
  target_id: string
  delivered_at: string
  read_at: string | null
}
export interface Overview {
  last_run: ReclaimRunView | null
  active_run: ReclaimRunView | null
  targets: ReclaimCandidate[]
  summary: null | {
    review_target_count: number
    new_candidate_count: number
    newly_notified_count: number
    needs_review_count: number
    unread_count: number
    unknown_cost_target_count: number
    monthly_saving_by_currency: Record<string, string>
  }
}
export function pathId(id: string): string {
  if (!uuid.test(id)) throw new ApiError('유효한 요청 번호가 아닙니다.', 404)
  return encodeURIComponent(id)
}
// Validate decision-critical fields at the HTTP boundary; generated TS alone is not validation.
function envelope(value: unknown, key: 'problem_id' | 'run_id', expected?: string): Record<string, any> {
  const x = value as Record<string, any>
  if (
    !x ||
    x.schema_version !== 2 ||
    typeof x[key] !== 'string' ||
    !uuid.test(x[key]) ||
    (expected && x[key] !== expected) ||
    !Object.hasOwn(statuses, x.status) ||
    typeof x.message !== 'string'
  )
    throw new Error('서버 응답 형식을 확인하지 못했습니다.')
  return x
}
export function access(value: unknown, expected?: string): AccessView {
  const x = envelope(value, 'problem_id', expected)
  if (
    x.task_type !== 'ACCESS_REQUEST' ||
    !Array.isArray(x.approval_steps) ||
    x.total_steps !== x.approval_steps.length
  )
    throw new Error('승인 단계 응답을 확인하지 못했습니다.')
  if (
    x.approval_steps.some(
      (s: any, i: number) =>
        !s ||
        s.step !== i + 1 ||
        typeof s.approver_id !== 'string' ||
        !uuid.test(s.approver_id) ||
        !['PENDING', 'WAITING', 'APPROVED', 'REJECTED', 'ON_HOLD', 'SKIPPED'].includes(s.status)
    )
  )
    throw new Error('승인 단계 응답을 확인하지 못했습니다.')
  if (
    x.status === 'WAITING_APPROVAL' &&
    (typeof x.plan_hash !== 'string' ||
      !/^[0-9a-f]{64}$/.test(x.plan_hash) ||
      !Number.isSafeInteger(x.plan_version) ||
      x.plan_version < 1 ||
      x.approval_steps.filter((s: any) => s.status === 'WAITING').length !== 1 ||
      !x.approval_steps.some((s: any) => s.status === 'WAITING' && s.step === x.current_step))
  )
    throw new Error('현재 승인 계획을 확인하지 못했습니다.')
  return x as AccessView
}
export function run(value: unknown, expected?: string): ReclaimRunView {
  const x = envelope(value, 'run_id', expected)
  if (x.task_type !== 'RECLAIM_SCAN' || ['WAITING_APPROVAL', 'ON_HOLD', 'REJECTED', 'MANUAL_REVIEW'].includes(x.status))
    throw new Error('점검 상태 응답을 확인하지 못했습니다.')
  return x as ReclaimRunView
}
const submissions = new Submission()
export const phase2 = {
  catalog: () => api<CatalogItem[]>('/v2/problems/catalog'),
  summaries: async () =>
    (await api<AccessSummary[]>('/v2/problems/summaries')).map((x) => ({
      ...x,
      workflow: access(x.workflow)
    })),
  report: async (id: string) => {
    const x = await api<AccessReport>(`/v2/problems/${pathId(id)}/report`)
    return { ...x, workflow: access(x.workflow, id) }
  },
  submit: (owner: string, input: AccessRequestInput) =>
    submissions.submit(owner, 'access', input, async (body, key) =>
      access(await api('/v2/problems', { method: 'POST', body, headers: { 'Idempotency-Key': key } }))
    ),
  decide: async (id: string, input: ApprovalDecisionInput) =>
    access(
      await api(`/v2/problems/${pathId(id)}/decisions`, { method: 'POST', body: JSON.stringify(input) }),
      id
    ),
  resume: async (id: string) =>
    access(await api(`/v2/problems/${pathId(id)}/resume`, { method: 'POST' }), id),
  scopes: () => api<Scope[]>('/reclaim/scopes'),
  overview: async () => {
    const x = await api<Overview>('/reclaim/overview')
    if (x.active_run) run(x.active_run)
    if (x.last_run) run(x.last_run)
    return x
  },
  start: (owner: string, scope: string) =>
    submissions.submit(owner, 'reclaim', { scope_id: scope }, async (body, key) =>
      run(await api('/reclaim/runs', { method: 'POST', body, headers: { 'Idempotency-Key': key } }))
    ),
  run: async (id: string) => run(await api(`/reclaim/runs/${pathId(id)}`), id),
  items: (id: string) => api<ReclaimCandidate[]>(`/reclaim/runs/${pathId(id)}/items`),
  target: (id: string) => api<ReclaimCandidate>(`/reclaim/targets/${pathId(id)}`),
  notifications: () => api<Notification[]>('/reclaim/notifications'),
  read: (id: string) =>
    api<{ read_at: string }>(`/reclaim/notifications/${pathId(id)}/read`, { method: 'PATCH' })
}
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
    if (e.status === 403) return '이 업무를 처리할 권한이 없습니다.'
    if (e.status === 404) return '요청한 항목을 찾을 수 없습니다.'
    if (e.status === 409) return '상태 또는 승인 계획이 변경되었습니다. 최신 내용을 확인해 주세요.'
  }
  return e instanceof Error ? e.message : '불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
}
export const stopPolling = (e: unknown) => e instanceof ApiError && [401, 403, 404].includes(e.status)
