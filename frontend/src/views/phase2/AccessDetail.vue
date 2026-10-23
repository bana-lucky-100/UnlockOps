<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import Workspace from '../../components/phase2/Workspace.vue'
import WorkflowBadge from '../../components/phase2/WorkflowBadge.vue'
import EvidenceList from '../../components/phase2/EvidenceList.vue'
import { phase2, errorMessage, stopPolling, type AccessReport } from '../../phase2/api'
import { approvalLabels, canDecide, platforms, when } from '../../phase2/presentation'
import type { ApprovalDecisionInput } from '../../contracts/phase2'
import { currentUser } from '../../session'
import { usePolling } from '../../lib/polling'
const id = String(useRoute().params.id)
const report = ref<AccessReport | null>(null),
  loadError = ref(''),
  actionError = ref(''),
  message = ref(''),
  busy = ref(false),
  reason = ref('')
const workflow = computed(() => report.value?.workflow)
const deciding = computed(
  () =>
    !loadError.value && !busy.value && !!workflow.value && canDecide(workflow.value, currentUser.value?.id)
)
const resumable = computed(
  () =>
    !loadError.value &&
    !busy.value &&
    workflow.value &&
    ['ON_HOLD', 'MANUAL_REVIEW'].includes(workflow.value.status)
)
const polling = usePolling(async () => {
  if (busy.value) return true
  try {
    const next = await phase2.report(id)
    if (busy.value) return true
    report.value = next
    loadError.value = ''
    return !['DONE', 'REJECTED', 'FAILED'].includes(next.workflow.status)
  } catch (e) {
    loadError.value = errorMessage(e)
    if (stopPolling(e)) {
      report.value = null
      return false
    }
    throw e
  }
})
async function act(action: ApprovalDecisionInput['action'] | 'RESUME') {
  const value = workflow.value,
    owner = currentUser.value?.id
  if (!value || !owner || busy.value || loadError.value) return
  if (action !== 'RESUME' && !deciding.value) return
  if (action === 'RESUME' && !resumable.value) return
  if ((action === 'REJECT' || action === 'HOLD') && !reason.value.trim()) {
    actionError.value = '반려·보류 사유를 입력해 주세요.'
    return
  }
  busy.value = true
  actionError.value = ''
  message.value = ''
  try {
    if (action === 'RESUME') await phase2.resume(id)
    else
      await phase2.decide(id, {
        action,
        expected_plan_hash: value.plan_hash!,
        expected_plan_version: value.plan_version!,
        reason: reason.value.trim() || null
      })
    if (currentUser.value?.id !== owner) return
    message.value = action === 'RESUME' ? '최신 조건으로 재분석을 요청했습니다.' : '검토 결과를 저장했습니다.'
    reason.value = ''
  } catch (e) {
    if (currentUser.value?.id === owner) actionError.value = errorMessage(e)
  } finally {
    // Retire the displayed approval card even on conflict or response loss; never retry a decision automatically.
    report.value = null
    busy.value = false
    polling.restart()
  }
}
const approverName = (id: string) => report.value?.approvers.find((x) => x.id === id)?.name || id
const eventLabel = (kind: string) =>
  ({
    V2_REQUESTED: '요청 접수',
    V2_DECISION: '승인 검토 결과 저장',
    V2_RESUMED: '재분석 요청',
    V2_PLAN_REVIEW_REQUIRED: '승인 조건 변경',
    V2_MOCK_GRANTED: '권한 반영 기록'
  })[kind] || '처리 기록'
</script>
<template>
  <Workspace>
    <RouterLink class="p2-link" to="/access">← 요청 목록</RouterLink>
    <header class="p2-heading p2-row" style="margin-top: 20px">
      <h1>요청 상세</h1>
      <WorkflowBadge v-if="workflow" :value="workflow" />
    </header>
    <div v-if="loadError" class="p2-alert" role="alert">
      {{ loadError }} <button class="p2-btn" @click="polling.restart">다시 불러오기</button>
    </div>
    <p v-if="actionError" class="p2-alert" role="alert">{{ actionError }}</p>
    <p v-if="message" class="p2-notice" role="status">{{ message }}</p>
    <p v-if="!report && !loadError" role="status">최신 요청을 확인하고 있습니다.</p>
    <div v-if="report && workflow" class="p2-grid">
      <div class="p2-stack">
        <section class="p2-card">
          <div class="p2-row">
            <h2>{{ platforms[report.platform] }} 요청</h2>
            <span>{{ report.requester_name }}</span>
          </div>
          <p class="p2-prose">{{ report.contents }}</p>
          <small>{{ when(report.created_at) }} · 요청 {{ id }}</small>
        </section>
        <section class="p2-card" aria-live="polite">
          <h2>현재 처리 결과</h2>
          <p class="p2-prose">{{ workflow.message }}</p>
          <p v-if="workflow.verification_ok === false" class="p2-alert">
            권한 반영을 확인하지 못했습니다. 담당자의 확인이 필요합니다.
          </p>
        </section>
        <section v-if="report.analysis_summary" class="p2-card">
          <h2>승인 검토 보고서</h2>
          <p class="p2-prose">{{ report.analysis_summary }}</p>
        </section>
        <section class="p2-card">
          <h2>정책 근거</h2>
          <EvidenceList :items="report.policy_evidence" />
        </section>
        <section class="p2-card">
          <h2>처리 이력</h2>
          <ol v-if="report.history.length">
            <li v-for="event in report.history" :key="event.id">
              {{ eventLabel(event.kind) }} <small>{{ when(event.created_at) }}</small>
            </li>
          </ol>
          <p v-else class="p2-muted">등록된 이력이 없습니다.</p>
        </section>
      </div>
      <aside class="p2-stack">
        <section v-if="report.plan" class="p2-card">
          <h2>검토 대상 계획</h2>
          <dl>
            <dt>자원</dt>
            <dd>{{ report.resource_name || report.plan.resource_id }}</dd>
            <dt>권한</dt>
            <dd>{{ report.entitlement_code || report.plan.entitlement_id }}</dd>
            <dt>월 예상 비용</dt>
            <dd>{{ report.plan.monthly_amount }} {{ report.plan.currency }}</dd>
            <dt>산정 기준</dt>
            <dd>
              {{
                {
                  SEAT_MONTHLY: '월 좌석 비용',
                  USAGE_ESTIMATE: '사용량 예상 예산',
                  NO_ADDITIONAL_COST: '추가 비용 없음'
                }[report.plan.cost_basis]
              }}
            </dd>
            <dt>계획 버전</dt>
            <dd>{{ workflow.plan_version }}</dd>
          </dl>
          <p v-if="report.plan.cost_basis === 'USAGE_ESTIMATE'" class="p2-muted">
            실제 사용량 청구액과 다를 수 있습니다.
          </p>
        </section>
        <section class="p2-card">
          <h2>승인 순서</h2>
          <ol v-if="workflow.approval_steps?.length" class="p2-steps">
            <li v-for="step in workflow.approval_steps" :key="step.step" :data-status="step.status">
              <div class="p2-row">
                <strong>{{ step.step }}차 · {{ approverName(step.approver_id) }}</strong
                ><span>{{ approvalLabels[step.status] }}</span>
              </div>
              <p v-if="step.reason" class="p2-prose">{{ step.reason }}</p>
              <small v-if="step.acted_at">{{ when(step.acted_at) }}</small>
            </li>
          </ol>
          <p v-else class="p2-muted">현재 승인 단계가 없습니다.</p>
        </section>
        <section v-if="deciding" class="p2-card">
          <h2>내 승인 차례</h2>
          <p class="p2-muted">
            {{
              workflow.current_step === 1
                ? '업무 필요성과 요청 범위를 검토해 주세요.'
                : '규정·허용 권한·비용 및 앞선 검토 내용을 확인해 주세요.'
            }}
          </p>
          <label
            >검토 사유 <small>반려·보류 시 필수</small><textarea v-model="reason" maxlength="2000" rows="4" />
          </label>
          <div class="p2-actions">
            <button class="p2-btn primary" @click="act('APPROVE')">승인</button
            ><button class="p2-btn" @click="act('HOLD')">보류</button
            ><button class="p2-btn danger" @click="act('REJECT')">반려</button>
          </div>
        </section>
        <section v-if="resumable" class="p2-card">
          <h2>최신 조건으로 재검토</h2>
          <p>보류 사유를 해결했다면 재분석을 요청하세요. 새 계획에 대해 다시 승인받게 됩니다.</p>
          <button class="p2-btn primary" @click="act('RESUME')">재분석 요청</button>
        </section>
        <p v-if="busy" role="status">처리 중입니다…</p>
      </aside>
    </div>
  </Workspace>
</template>
