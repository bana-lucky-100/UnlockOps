import { api, type ApprovalSummary, type Platform, type Problem } from '../api'
import { phase2 } from '../phase2/api'
import { currentUser } from '../session'
import { fromV2, isMyStep } from './v2view.ts'

export { fromV2 }

/**
 * 화면이 쓰는 데이터 입구. 화면(뷰)은 그대로 두고, 로그인한 계정의 세대에 따라 API만 바꾼다.
 * - v2(Phase 2 계정, 기본): #29의 /v2/problems · 응답 검증(phase2/api.ts)을 그대로 쓰고, 화면이 쓰는 Problem 모양으로 옮긴다.
 * - v1(workflow_version === 1, 구 계정): 기존 /problems API.
 * 상태 · 완료 판정은 서버 값을 그대로 옮기고, 여기서 추측해서 바꾸지 않는다.
 */
export const isV2 = () => currentUser.value?.workflow_version !== 1

/** 내 요청(요청자). */
export async function listMine(): Promise<Problem[]> {
  if (!isV2()) return api<Problem[]>('/problems?mine=true')
  const me = currentUser.value?.id
  return (await phase2.summaries()).filter(x => x.requester_id === me).map(fromV2)
}

/** 승인함(승인자): 서버가 보여 줄 수 있는 요청 전체. */
export async function listForApprover(): Promise<Problem[]> {
  if (!isV2()) return api<Problem[]>('/problems')
  return (await phase2.summaries()).map(fromV2)
}

/** 승인함 상단 요약. v2에는 요약 API가 없어서 목록에서 이번 주 건수를 센다. */
export async function approvalSummary(list: Problem[]): Promise<ApprovalSummary> {
  if (!isV2()) return api<ApprovalSummary>('/approvals/summary')
  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000
  const week = list.filter(p => Date.parse(p.created_at) >= weekAgo)
  return {
    department: currentUser.value?.department ?? '',
    memberCount: new Set(list.map(p => p.requester_name)).size,
    weekRequests: week.length,
    approved: week.filter(p => p.status === 'DONE').length,
    rejected: week.filter(p => p.status === 'REJECTED').length,
    failed: week.filter(p => p.status === 'FAILED').length,
  }
}

export async function getProblem(id: string): Promise<Problem> {
  if (!isV2()) return api<Problem>(`/problems/${encodeURIComponent(id)}`)
  return fromV2(await phase2.report(id))
}

/** 지금 이 사용자가 결정할 차례인지. v2는 서버가 정한 현재 단계 승인자만(#29 canDecide와 같은 기준). */
export function myTurn(p: Problem): boolean {
  if (!isV2()) return p.status === 'WAITING_APPROVAL'
  return isMyStep(p, currentUser.value?.id)
}

export type Decision = 'APPROVE' | 'REJECT' | 'HOLD'
/** 승인 · 반려 · 보류. 화면에 보여 준 계획(plan_hash · plan_version)에 대해서만 결정한다(바뀌었으면 서버가 409). */
export async function decide(p: Problem, action: Decision, reason: string): Promise<void> {
  if (!isV2()) {
    if (action === 'HOLD') throw new Error('이 계정에서는 보류를 지원하지 않아요.')
    await api(`/problems/${encodeURIComponent(p.id)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approved: action === 'APPROVE', expectedPlanHash: p.plan_hash, reason }),
    })
    return
  }
  if (!p.plan_hash || !p.plan_version) throw new Error('승인 계획을 확인하지 못했어요. 새로 불러온 뒤 다시 결정해 주세요.')
  await phase2.decide(p.id, { action, expected_plan_hash: p.plan_hash, expected_plan_version: p.plan_version, reason: reason.trim() || null })
}

/** 보류 · 담당자 검토를 최신 조건으로 다시 분석. v2 전용. */
export async function resume(p: Problem): Promise<void> {
  await phase2.resume(p.id)
}

/** 요청 보내기. v2는 #29의 멱등 키 처리(Submission)를 그대로 쓴다. 성공하면 상세로 갈 id를 돌려준다. */
export async function submitV2(platform: Platform, contents: string): Promise<string | null> {
  const owner = currentUser.value?.id
  if (!owner) throw new Error('로그인이 끝났어요. 다시 로그인해 주세요.')
  const view = await phase2.submit(owner, { schema_version: 2, platform: platform as never, contents })
  return currentUser.value?.id === owner && view ? view.problem_id : null
}
