// api는 화면에서 부를 때만 불러온다(이 파일의 계산 함수를 node 테스트에서 바로 쓰기 위해).
const api = async <T>(path: string, init?: RequestInit) => (await import('../api.ts')).api<T>(path, init)
import { MOCK } from './mock.ts'

/**
 * S-04 오늘의 회수 점검. 계약 초안 (지성님 확인 중):
 *   POST /api/revocation-checks          → { run_id }            ([지금 실행])
 *   GET  /api/revocation-checks/latest   → RevocationReport
 * 후보와 월 절감액은 백엔드가 SQL로 계산하고, reason(사유 요약)만 AI가 쓴다.
 * 실제 회수(권한 삭제)는 하지 않는다. 화면은 읽기와 알림까지만.
 */
import type { Status } from '../api.ts'

/**
 * 공통 규격(테스트 시나리오 문서 2 · 5절):
 * - 점검 실행은 task_type RECLAIM_SCAN의 처리 상태(status · reason_code)를 쓴다.
 *   완료는 DONE / SCAN_COMPLETED(신규 후보 알림) 또는 DONE / NO_NEW_CANDIDATES. 실패는 FAILED / SCAN_FAILED · NOTIFICATION_FAILED.
 * - 후보 하나하나는 candidate_status(PENDING_REVIEW · RETAINED · EXCLUDED)로 따로 관리한다.
 * - "이번에 새로 알린 후보"와 "이미 알린 후보"는 상태값이 아니라 알림 시각(notified_at)으로 나눈다.
 */
export type CandidateStatus = 'PENDING_REVIEW' | 'RETAINED' | 'EXCLUDED'

export interface RevocationCandidate {
  id: string; user_id: string; user_name: string; platform: string; resource: string
  tf_id: string | null; last_used_at: string | null; monthly_cost: number
  reason: string; policy_ref: string
  candidate_status: CandidateStatus
  candidate_reason_code: string            // TF_ENDED_UNUSED_30D, EMPLOYEE_LEFT …
  exclusion_reason_code?: string | null    // ACTIVE_OTHER_TF, RETENTION_APPROVED, USAGE_RESUMED
  notified_at: string | null               // 알림 성공 시각. 저장 · 전송 시도만으로는 채우지 않는다
  already_notified?: boolean               // v2: 이번 점검에서 ALREADY_NOTIFIED로 건너뛴 후보
  cost_known?: boolean                     // v2: 비용 미확인이면 false. 0원으로 계산하지 않는다
}
export interface ScanRun {
  id: string; task_type: 'RECLAIM_SCAN'; trigger: 'SCHEDULE' | 'MANUAL' | 'UNKNOWN'
  status: Status; reason_code: string | null; started_at: string; finished_at: string | null
}
/**
 * 정보가 부족해 후보 판정을 못 한 건. 알림에서는 빼고 보고서에만 남긴다(필드 이름은 민지님 확인 중).
 * 회수 점검은 MANUAL_REVIEW를 쓰지 않는다(10/23 합의): 추가 확인이 1건 이상이면 DONE / SCAN_COMPLETED,
 * NO_NEW_CANDIDATES는 추가 확인 0건일 때만, 점검 전체를 판단할 수 없으면 FAILED / SCAN_FAILED.
 */
// v4 문서 제안 필드: employee_name · resource_name · missing(코드). 확정 전이라 예전 이름(user_name · platform)도 받는다.
export interface NeedsReview { employee_name?: string; resource_name?: string; user_name?: string; platform?: string; missing: string[] }
/** missing 코드 → 화면 문구. 코드값은 민지님 확정 대기라 모르는 값은 그대로 보여 준다. */
export const MISSING_TEXT: Record<string, string> = {
  LAST_USED_AT: '마지막 사용일', LAST_ACTIVITY_AT: '마지막 사용일', TF_END_DATE: '소속 TF 종료일', TF_ENDED_AT: '소속 TF 종료일',
  TF_MEMBERSHIP: 'TF 소속 정보', RETENTION_APPROVAL: '유지 승인 여부', EMPLOYMENT_STATUS: '재직 여부', SEAT_PRICE: '좌석 비용',
  // v2 계약(contracts/phase2.ts NeedsReviewItem.missing)
  USAGE_OBSERVATION: '사용 기록', PRICE_EVIDENCE: '비용 근거', RECLAIM_FACTS: '회수 판단 근거',
}
export function needsReviewRow(n: NeedsReview) {
  return { who: n.employee_name ?? n.user_name ?? '이름 없음', what: n.resource_name ?? n.platform ?? '', missing: n.missing.map(m => MISSING_TEXT[m] ?? m) }
}
export interface RevocationReport {
  run: ScanRun | null
  summary: { new_count: number; monthly_saving: number; needs_review_count?: number }
  candidates: RevocationCandidate[]   // PARTIAL(FAILED / SCAN_FAILED)이어도 그때까지 찾은 후보를 담는다
  needs_review?: NeedsReview[]
  scan_complete?: boolean             // v4 제안: PARTIAL이면 false
}

/** 이번 점검에서 처음 알린 후보: 담당자 판단 대기 중이고, 알림 시각이 이번 점검 시작 뒤. */
export function isNewInRun(c: RevocationCandidate, run: ScanRun | null): boolean {
  return c.candidate_status === 'PENDING_REVIEW' && !!c.notified_at && !c.already_notified && !!run && c.notified_at >= run.started_at
}
/** 앞선 점검에서 이미 알렸고 아직 담당자 판단을 기다리는 후보. 다시 알리지 않는다. */
export function isAlreadyNotified(c: RevocationCandidate, run: ScanRun | null): boolean {
  // 알림 성공 시각이 있는 후보만. 아직 알리지 못한 후보(notified_at 없음)는 '전체' 탭에만 '알림 전'으로 보인다.
  return c.candidate_status === 'PENDING_REVIEW' && !!c.notified_at && !isNewInRun(c, run)
}
export const EXCLUSION_TEXT: Record<string, string> = {
  ACTIVE_OTHER_TF: '다른 TF에서 사용 중',
  RETENTION_APPROVED: '유지 승인됨',
  USAGE_RESUMED: '다시 사용 시작',
}
export const CANDIDATE_REASON_TEXT: Record<string, string> = {
  TF_ENDED_UNUSED_30D: 'TF 종료 후 30일 이상 미사용',
  EMPLOYEE_LEFT: '퇴사자 계정',
}
/** 일부만 조회된 실패: FAILED / SCAN_FAILED인데 찾은 후보가 있다. 실패를 알리고 찾은 후보는 보여 준다. */
export function isPartial(r: RevocationReport | null): boolean {
  if (!r?.run || r.run.status !== 'FAILED' || r.run.reason_code !== 'SCAN_FAILED') return false
  return r.scan_complete === false || r.candidates.length > 0
}
/** 추가 확인 건수. 응답에 개수가 없으면 목록 길이로 센다. */
export function needsReviewCount(r: RevocationReport | null): number {
  return r?.summary.needs_review_count ?? r?.needs_review?.length ?? 0
}
/** 점검 실행이 아직 진행 중인지(접수 · 후보 선별 · 결과 저장 · 알림). */
export function isRunning(run: ScanRun | null): boolean {
  return !!run && (run.status === 'RECEIVED' || run.status === 'DIAGNOSING' || run.status === 'EXECUTING')
}

const daysAgo = (d: number) => new Date(Date.now() - d * 86_400_000).toISOString()
const today9 = () => { const t = new Date(); t.setHours(9, 0, 0, 0); return t.toISOString() }

/** 목업: 회수 시나리오(결제 개편 TF 종료, 김지성 Copilot 47일 미사용)와 같은 값. 제외 예시(다른 TF 사용 중)도 하나 둔다. */
function mockReport(trigger: 'SCHEDULE' | 'MANUAL'): RevocationReport {
  const at = trigger === 'MANUAL' ? new Date().toISOString() : today9()
  const base = { candidate_reason_code: 'TF_ENDED_UNUSED_30D', policy_ref: 'POL-06 제5조 (시연 가정)', exclusion_reason_code: null }
  return {
    run: { id: 'mock-run', task_type: 'RECLAIM_SCAN', trigger, status: 'DONE', reason_code: 'SCAN_COMPLETED', started_at: at, finished_at: at },
    summary: { new_count: 1, monthly_saving: 19, needs_review_count: 1 },
    needs_review: [{ employee_name: '이운영', resource_name: 'Notion 팀 좌석', missing: ['LAST_USED_AT', 'TF_END_DATE'] }],
    candidates: [
      { ...base, id: 'c1', user_id: 'E-001', user_name: '김지성', platform: 'GitHub Copilot', resource: 'Copilot 좌석', tf_id: '결제 개편 TF',
        last_used_at: daysAgo(47), monthly_cost: 19, candidate_status: 'PENDING_REVIEW', notified_at: at,
        reason: '결제 개편 TF가 끝난 뒤 47일 동안 사용 기록이 없고, 다른 TF 소속이나 유지 승인이 없어요.' },
      { ...base, id: 'c2', user_id: 'E-005', user_name: '정데이터', platform: 'Tableau Cloud', resource: '대시보드 작성 좌석', tf_id: '분기 보고 TF',
        last_used_at: daysAgo(62), monthly_cost: 80, candidate_status: 'PENDING_REVIEW', notified_at: daysAgo(3),
        reason: '분기 보고 TF 종료 후 62일 동안 사용 기록이 없어요.' },
      { ...base, id: 'c3', user_id: 'E-004', user_name: '최코파', platform: 'Figma', resource: 'Dev 좌석', tf_id: null,
        last_used_at: daysAgo(41), monthly_cost: 25, candidate_status: 'PENDING_REVIEW', notified_at: daysAgo(1),
        reason: '소속 TF가 없고 41일 동안 사용 기록이 없어요.' },
      { ...base, id: 'c4', user_id: 'E-007', user_name: '오개발', platform: 'GitHub Copilot', resource: 'Copilot 좌석', tf_id: '결제 개편 TF',
        last_used_at: daysAgo(35), monthly_cost: 19, candidate_status: 'EXCLUDED', exclusion_reason_code: 'ACTIVE_OTHER_TF', notified_at: null,
        reason: '결제 개편 TF는 끝났지만 추천 모델 TF에서 계속 쓰고 있어 후보에서 뺐어요.' },
    ],
  }
}

let mockState: RevocationReport | null = null

/** v2(Phase 2) 계정인지. 세션은 화면에서만 불러온다(node 테스트용). */
async function v2(): Promise<boolean> {
  const { currentUser } = await import('../session.ts')
  return currentUser.value?.workflow_version !== 1
}

/** 문자열 금액 → 숫자. 비용 미확인이면 null. */
const money = (v: string | null | undefined) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v))

/**
 * v2 회수 개요(GET /reclaim/overview, #29) → 화면 보고서.
 * - 신규/이미 알림 구분: 이번 점검 스냅샷 시각(as_of) 뒤에 알린 후보 = 신규. 이미 알린 후보(ALREADY_NOTIFIED)는 다시 알리지 않는다.
 * - 개요 응답에는 대상자 이름 · 자원 이름이 없어서, 사유 문장(explanation)으로 대신 보여 준다.
 */
export function fromOverview(o: {
  last_run: any | null; active_run: any | null; targets: any[]
  summary: null | { new_candidate_count: number; needs_review_count: number; monthly_saving_by_currency: Record<string, string> }
}, label: (platform: string) => string = p => p): RevocationReport {
  const r = o.active_run ?? o.last_run
  const asOf = r?.as_of ?? ''
  const usd = money(o.summary?.monthly_saving_by_currency?.USD) ?? 0
  return {
    run: r ? { id: r.run_id, task_type: 'RECLAIM_SCAN', trigger: 'UNKNOWN', status: r.status, reason_code: r.reason_code ?? null, started_at: asOf, finished_at: null } : null,
    summary: { new_count: o.summary?.new_candidate_count ?? r?.new_candidate_count ?? 0, monthly_saving: usd, needs_review_count: o.summary?.needs_review_count ?? r?.needs_review_count },
    needs_review: (r?.needs_review ?? []).map((n: any) => ({ employee_name: n.employee_name, resource_name: n.resource_name, missing: n.missing ?? [] })),
    scan_complete: r?.scan_complete,
    candidates: o.targets.map((t: any) => {
      const cost = t.cost_impact?.status === 'ESTIMATED' && t.cost_impact.currency === 'USD' ? money(t.cost_impact.monthly_amount) : null
      const already = t.skip_reason_code === 'ALREADY_NOTIFIED'
      return {
        id: t.target_id ?? t.assignment_id, user_id: '', user_name: '대상자', platform: label(t.platform), resource: '',
        tf_id: null, last_used_at: null, monthly_cost: cost ?? 0, cost_known: cost !== null,
        reason: t.explanation, policy_ref: (t.policy_evidence ?? []).map((e: any) => `${e.doc_id} ${e.article}`).join(' · '),
        candidate_status: t.candidate_status ?? 'PENDING_REVIEW', candidate_reason_code: t.candidate_reason_code ?? '',
        exclusion_reason_code: t.exclusion_reason_code ?? null,
        notified_at: t.notified_at ?? null,
        already_notified: already,
      }
    }),
  }
}

async function v2Report(): Promise<RevocationReport> {
  const [{ phase2 }, { platformOf }] = await Promise.all([import('../phase2/api.ts'), import('./platforms.ts')])
  return fromOverview(await phase2.overview(), p => platformOf(p).label)
}

export async function latestReport(): Promise<{ report: RevocationReport; mock: boolean }> {
  if (MOCK) return { report: (mockState ??= mockReport('SCHEDULE')), mock: true }
  if (await v2()) return { report: await v2Report(), mock: false }
  return { report: await api<RevocationReport>('/revocation-checks/latest'), mock: false }
}

export async function runNow(): Promise<{ report: RevocationReport; mock: boolean }> {
  if (MOCK) {
    await new Promise(r => setTimeout(r, 900))
    // 09:00 점검에서 이미 알린 후보는 다시 점검해도 신규로 알리지 않는다(notified_at). 시연에서 그 차이가 보이게 한다.
    const prev = mockState
    const next = mockReport('MANUAL')
    if (prev) {
      // 같은 후보는 알림 시각을 그대로 두고(다시 알리지 않음). 목업 재점검에서는 추가 확인 건도 정리됐다고 가정해
      // DONE / NO_NEW_CANDIDATES(추가 확인 0건일 때만 쓰는 값)로 끝낸다.
      next.candidates = prev.candidates.map(c => ({ ...c }))
      next.needs_review = []
      next.run = { ...next.run!, reason_code: 'NO_NEW_CANDIDATES' }
      next.summary = { new_count: 0, monthly_saving: 0, needs_review_count: 0 }
    }
    mockState = next
    return { report: next, mock: true }
  }
  if (await v2()) {
    // 담당 범위(scope) 중 켜진 첫 범위로 점검한다(#29: 같은 요청은 멱등 키로 한 번만 접수). 끝날 때까지 2초마다 확인(최대 1분).
    const [{ phase2 }, { currentUser }] = await Promise.all([import('../phase2/api.ts'), import('../session.ts')])
    const owner = currentUser.value?.id
    const scopes = await phase2.scopes()
    const scope = pickScope(scopes)
    if (!owner || !scope) throw new Error('점검할 담당 범위가 없어요.')
    await phase2.start(owner, scope.id)
    for (let i = 0; i < 30; i++) {
      const report = await v2Report()
      if (!isRunning(report.run)) return { report, mock: false }
      await new Promise(r => setTimeout(r, 2000))
    }
    return { report: await v2Report(), mock: false }
  }
  await api<{ run_id: string }>('/revocation-checks', { method: 'POST' })
  return latestReport()
}

/**
 * 수동 점검할 범위 고르기. 켜진 범위 → 기본 유료 좌석 범위(scope_key …:paid-seats) → 첫 범위 순서.
 * 시드에는 평가용 범위(R-02 · X-11 · MISSING_USAGE 등)가 함께 있고 목록이 scope_key 순이라,
 * '첫 범위'만 고르면 대문자 키인 평가용 범위가 먼저 잡혀 R-01(기본 점검) 대신 다른 시나리오가 돌았다.
 */
export function pickScope<T extends { scope_key: string; enabled: boolean }>(scopes: T[]): T | undefined {
  return scopes.find(s => s.enabled) ?? scopes.find(s => s.scope_key.endsWith(':paid-seats')) ?? scopes[0]
}

export function daysSince(iso: string | null): number | null {
  if (!iso) return null
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000))
}
