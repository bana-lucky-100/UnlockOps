import type {
  AccessView,
  ApprovalStatus,
  CostImpact,
  ReclaimCandidate,
  ReclaimRunView,
  Status,
  Platform
} from '../contracts/phase2'

export const platforms: Record<Platform, string> = {
  SNOWFLAKE: 'Snowflake',
  DATABRICKS: 'Databricks',
  SALESFORCE: 'Salesforce',
  DATADOG: 'Datadog',
  TABLEAU_CLOUD: 'Tableau Cloud',
  FIGMA: 'Figma',
  GITHUB: 'GitHub',
  JIRA: 'Jira',
  SLACK: 'Slack',
  NOTION: 'Notion'
}
export const approvalLabels: Record<ApprovalStatus, string> = {
  PENDING: '순서 대기',
  WAITING: '검토 중',
  APPROVED: '승인',
  REJECTED: '반려',
  ON_HOLD: '보류',
  SKIPPED: '종료'
}
export const statuses: Record<Status, string> = {
  RECEIVED: '접수',
  DIAGNOSING: '분석 중',
  WAITING_APPROVAL: '승인 대기',
  ON_HOLD: '보류',
  EXECUTING: '처리 중',
  DONE: '완료',
  REJECTED: '반려',
  MANUAL_REVIEW: '담당자 검토',
  FAILED: '실패'
}
export const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function statusLabel(view: AccessView | ReclaimRunView): string {
  if ('run_id' in view)
    return view.status === 'DONE'
      ? '점검 완료'
      : view.status === 'EXECUTING'
        ? '결과 저장·알림 처리 중'
        : statuses[view.status]
  if (view.status === 'DONE')
    return view.result_type === 'GUIDANCE'
      ? '안내 완료'
      : view.result_type === 'ACCESS_VERIFIED' && view.verification_ok === true
        ? '권한 반영 확인'
        : '완료 상태 확인 필요'
  return view.status === 'EXECUTING' ? '권한 반영·검증 중' : statuses[view.status]
}
export function canDecide(view: AccessView, actor?: string): boolean {
  const waiting = view.approval_steps?.filter((s) => s.status === 'WAITING') ?? []
  return (
    !!actor &&
    view.status === 'WAITING_APPROVAL' &&
    !!view.plan_hash &&
    Number.isSafeInteger(view.plan_version) &&
    (view.plan_version ?? 0) > 0 &&
    waiting.length === 1 &&
    waiting[0].step === view.current_step &&
    waiting[0].approver_id === actor
  )
}
export function candidateLabel(item: ReclaimCandidate): string {
  return item.review_required || !item.candidate_status
    ? '근거 확인 필요'
    : { PENDING_REVIEW: '회수 검토 후보', RETAINED: '유지', EXCLUDED: '제외' }[item.candidate_status]
}
export function costLabel(cost: CostImpact): string {
  return cost.status === 'UNKNOWN' || cost.monthly_amount == null || !cost.currency
    ? '비용 미확인'
    : `${cost.monthly_amount} ${cost.currency} / 월 (예상)`
}
export function when(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '시각 확인 필요'
    : new Intl.DateTimeFormat('ko-KR', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Asia/Seoul'
      }).format(date)
}
export const help = {
  howto: [
    { t: '요청과 근거 확인', d: '업무 목적과 필요한 자원을 적고 분석 결과의 규정·비용을 확인하세요.' },
    {
      t: '순서대로 검토',
      d: '현재 지정된 승인자만 승인·반려·보류할 수 있습니다. 재개하면 최신 조건으로 다시 분석합니다.'
    },
    {
      t: '회수 후보 점검',
      d: '담당 범위의 후보와 미확인 근거를 확인하세요. 점검 완료는 실제 권한 회수를 의미하지 않습니다.'
    }
  ],
  faqs: [
    {
      q: '보류와 반려는 어떻게 다른가요?',
      a: '보류·담당자 검토 요청은 재분석할 수 있습니다. 반려 사유는 요청 상세에서 확인할 수 있습니다.'
    },
    {
      q: '표시된 비용은 실제 절감액인가요?',
      a: '회수 검토를 위한 월 예상 금액입니다. 미확인 비용은 0원으로 계산하지 않습니다.'
    }
  ]
}
