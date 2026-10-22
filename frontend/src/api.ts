export type Platform = 'GITHUB' | 'JIRA' | 'SLACK' | 'NOTION'
export type Status = 'RECEIVED' | 'DIAGNOSING' | 'WAITING_APPROVAL' | 'EXECUTING' | 'DONE' | 'REJECTED' | 'MANUAL_REVIEW' | 'FAILED'
export type ResultType = 'GUIDANCE' | 'ACCESS_VERIFIED'
export interface User { id: string; login_id: string; employee_no: string; name: string; role: 'REQUESTER'|'APPROVER'; job_grade: string; job_family: string; department: string }
export interface ApprovalSummary { department: string; memberCount: number; weekRequests: number; approved: number; rejected: number; failed: number }
export interface Evidence { doc_id?: string; article?: string; text?: string; source?: string; version?: string; kind?: string; [key: string]: unknown }
export interface Problem {
  id: string; platform: Platform; contents: string; status: Status; result_type?: ResultType|null; requester_name: string; employee_no: string;
  proposal?: string; diagnosis?: string; reason_code?: string; requested_role?: string; approver_id?: string;
  plan_hash?: string; verification_ok?: boolean|null; agent_mode?: string;
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
