export type Platform = 'GITHUB' | 'JIRA' | 'SLACK' | 'NOTION' | 'SNOWFLAKE' | 'DATABRICKS' | 'SALESFORCE' | 'DATADOG' | 'TABLEAU_CLOUD' | 'FIGMA'
// 공통 상태 규격(테스트 시나리오 문서) 9개. ON_HOLD = 보류(예산 부족 · 승인자 보류), 종료 아님.
export type Status = 'RECEIVED' | 'DIAGNOSING' | 'WAITING_APPROVAL' | 'ON_HOLD' | 'EXECUTING' | 'DONE' | 'REJECTED' | 'MANUAL_REVIEW' | 'FAILED'
export type ResultType = 'GUIDANCE' | 'ACCESS_VERIFIED'
export type StepStatus = 'PENDING' | 'WAITING' | 'APPROVED' | 'REJECTED' | 'ON_HOLD' | 'SKIPPED'
export interface ApprovalStep { step: number; approver_id: string | null; status: StepStatus; reason?: string | null; acted_at?: string | null }
export interface User { id: string; login_id: string; employee_no: string; name: string; role: 'REQUESTER'|'APPROVER'; job_grade: string; job_family: string; department: string; workflow_version?: 1|2; can_reclaim?: boolean }
export interface ApprovalSummary { department: string; memberCount: number; weekRequests: number; approved: number; rejected: number; failed: number }
export interface Evidence { doc_id?: string; article?: string; text?: string; source?: string; version?: string; kind?: string; [key: string]: unknown }
export interface Problem {
  id: string; platform: Platform; contents: string; status: Status; result_type?: ResultType|null; requester_name: string; employee_no: string;
  proposal?: string; diagnosis?: string; reason_code?: string; requested_role?: string; approver_id?: string;
  plan_hash?: string; plan_version?: number|null; verification_ok?: boolean|null; agent_mode?: string;
  // v2(Phase 2) 전용: 승인자 이름 · 월 비용. v1 서버는 보내지 않는다.
  approvers?: {id: string; name: string}[]; monthly_cost?: {amount: string; currency: string} | null; resource_name?: string | null;
  // 공통 규격 신규 필드. 서버가 아직 안 보내면 비어 있고, 화면은 기존 방식으로 표시한다.
  task_type?: 'ACCESS_REQUEST' | 'RECLAIM_SCAN'; message?: string | null;
  current_step?: number | null; total_steps?: number; approval_steps?: ApprovalStep[];
  created_at: string; updated_at: string; evidence?: Evidence[];
  decision_reason?: string|null; decided_at?: string|null; decided_by?: string|null;
  plan?: {resource_key: string; requested_role: string; resource_id?: string} | null;
  events?: {kind: string; payload: Record<string, unknown>; created_at: string}[]
}

/** 화면이 401(로그인 필요) · 403(권한 없음) · 409(이미 처리됨)를 구분해 안내할 수 있도록 상태 코드를 함께 던진다. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

let csrf = { token: '', headerName: 'X-XSRF-TOKEN' }
export async function refreshCsrf() {
  const response = await fetch('/api/auth/csrf', {credentials: 'same-origin'})
  if (!response.ok) throw new ApiError('보안 토큰을 불러오지 못했습니다.', response.status)
  csrf = await response.json()
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase()
  if (!['GET', 'HEAD'].includes(method) && !csrf.token) await refreshCsrf()
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (!['GET','HEAD'].includes(method)) headers.set(csrf.headerName, csrf.token)
  const response = await fetch('/api' + path, {
    ...options, credentials: 'same-origin',
    headers,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({message: '요청을 처리하지 못했습니다.'}))
    throw new ApiError(body.message || '요청을 처리하지 못했습니다.', response.status)
  }
  return response.status === 204 ? undefined as T : response.json()
}
