<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import Workspace from '../../components/phase2/Workspace.vue'
import WorkflowBadge from '../../components/phase2/WorkflowBadge.vue'
import CandidateCard from '../../components/phase2/CandidateCard.vue'
import {
  phase2,
  errorMessage,
  stopPolling,
  type Overview,
  type Scope,
  type Notification
} from '../../phase2/api'
import { platforms, when } from '../../phase2/presentation'
import { usePolling } from '../../lib/polling'
import { currentUser } from '../../session'
const router = useRouter()
const overview = ref<Overview | null>(null),
  scopes = ref<Scope[]>([]),
  notifications = ref<Notification[]>([])
const selected = ref(''),
  error = ref(''),
  actionError = ref(''),
  busy = ref(false),
  reading = ref(''),
  acceptedId = ref('')
const unread = computed(() => notifications.value.filter((n) => !n.read_at).length)
const polling = usePolling(async () => {
  try {
    const [next, permitted, inbox] = await Promise.all([
      phase2.overview(),
      phase2.scopes(),
      phase2.notifications()
    ])
    overview.value = next
    scopes.value = permitted
    notifications.value = inbox
    error.value = ''
    if (!permitted.some((x) => x.id === selected.value)) selected.value = permitted[0]?.id || ''
    return true
  } catch (e) {
    error.value = errorMessage(e)
    if (stopPolling(e)) {
      overview.value = null
      scopes.value = []
      notifications.value = []
      return false
    }
    throw e
  }
}, 5000)
async function start() {
  const owner = currentUser.value?.id
  if (!owner || !selected.value || busy.value || error.value || acceptedId.value) return
  busy.value = true
  actionError.value = ''
  acceptedId.value = ''
  try {
    const next = await phase2.start(owner, selected.value)
    if (currentUser.value?.id !== owner) return
    acceptedId.value = next.run_id
    await router.push(`/reclaim/runs/${next.run_id}`)
  } catch (e) {
    actionError.value = acceptedId.value
      ? '점검이 접수되었습니다. 아래에서 실행 상세를 열어 주세요.'
      : errorMessage(e)
  } finally {
    busy.value = false
    polling.restart()
  }
}
async function markRead(notification: Notification) {
  if (reading.value || notification.read_at || error.value) return
  reading.value = notification.id
  actionError.value = ''
  try {
    const result = await phase2.read(notification.id)
    notification.read_at = result.read_at
  } catch (e) {
    actionError.value = errorMessage(e)
  } finally {
    reading.value = ''
    polling.restart()
  }
}
</script>
<template>
  <Workspace>
    <header class="p2-heading">
      <h1>회수 점검·알림</h1>
      <p class="p2-muted">담당 범위의 미사용 좌석과 검토 근거를 확인하세요.</p>
    </header>
    <div v-if="error" class="p2-alert" role="alert">
      {{ error }} <button class="p2-btn" @click="polling.restart">다시 불러오기</button>
    </div>
    <p v-if="actionError" class="p2-alert" role="alert">{{ actionError }}</p>
    <p v-if="acceptedId" class="p2-notice">
      점검이 접수되었습니다.
      <RouterLink :to="`/reclaim/runs/${acceptedId}`" class="p2-link">실행 상세 열기 →</RouterLink>
    </p>
    <p v-if="!overview && !error" role="status">점검 현황을 불러오는 중입니다.</p>
    <div class="p2-grid">
      <div class="p2-stack">
        <section v-if="overview" class="p2-card">
          <h2>점검 현황</h2>
          <div v-if="overview.active_run" class="p2-notice">
            <WorkflowBadge :value="overview.active_run" />
            <p>{{ overview.active_run.message }}</p>
            <RouterLink class="p2-link" :to="`/reclaim/runs/${overview.active_run.run_id}`"
              >진행 중 점검 보기 →</RouterLink
            >
          </div>
          <div v-if="overview.last_run" style="margin-top: 16px">
            <div class="p2-row">
              <strong>최근 종료 점검</strong><WorkflowBadge :value="overview.last_run" />
            </div>
            <p>{{ overview.last_run.message }}</p>
            <RouterLink class="p2-link" :to="`/reclaim/runs/${overview.last_run.run_id}`"
              >전체 판정 보기 →</RouterLink
            >
          </div>
          <p v-if="!overview.last_run && !overview.active_run" class="p2-muted">
            조회 가능한 점검 이력이 없습니다.
          </p>
          <template v-if="overview.summary"
            ><div class="p2-metrics">
              <span
                >검토 대상<strong>{{ overview.summary.review_target_count }}건</strong></span
              ><span
                >최근 신규 후보<strong>{{ overview.summary.new_candidate_count }}건</strong></span
              ><span
                >비용 미확인<strong>{{ overview.summary.unknown_cost_target_count }}건</strong></span
              >
            </div>
            <h3>검토 대상 월 예상 금액</h3>
            <p v-for="(amount, currency) in overview.summary.monthly_saving_by_currency" :key="currency">
              {{ amount }} {{ currency }}
            </p>
            <p class="p2-muted">통화별 예상 금액이며 실제 회수·절감 완료 금액이 아닙니다.</p></template
          >
          <p v-else class="p2-muted">
            완료된 점검의 확정 집계가 없습니다. 미확인 항목은 실행 상세에서 확인하세요.
          </p>
        </section>
        <section class="p2-card">
          <h2>범위별 수동 점검</h2>
          <form @submit.prevent="start">
            <label
              >허용된 점검 범위<select v-model="selected" :disabled="busy || !scopes.length">
                <option value="" disabled>범위를 선택하세요</option>
                <option v-for="scope in scopes" :key="scope.id" :value="scope.id">
                  {{ scope.scope_key }} · {{ scope.platforms.map((p) => platforms[p]).join(', ') }}
                </option>
              </select></label
            >
            <p v-if="!scopes.length" class="p2-muted">
              전체 점검을 시작할 수 있는 범위가 없습니다. 플랫폼별 후보와 알림은 아래에서 확인하세요.
            </p>
            <p v-else class="p2-muted">
              선택 범위의 정기 점검: {{ scopes.find((s) => s.id === selected)?.enabled ? '사용' : '미사용' }}
            </p>
            <button
              class="p2-btn primary"
              :disabled="busy || !selected || !!error || !!acceptedId"
              type="submit"
            >
              {{ busy ? '접수 중…' : '후보 점검 시작' }}
            </button>
          </form>
        </section>
        <section>
          <h2>현재 검토 후보</h2>
          <div class="p2-stack">
            <CandidateCard
              v-for="item in overview?.targets"
              :key="item.target_id || item.assignment_id"
              :item="item"
              personal-read
            />
          </div>
          <p v-if="overview && !overview.targets.length" class="p2-empty">
            현재 조회 가능한 검토 후보가 없습니다. 미확인·제외·유지 행은 실행 상세에서 확인하세요.
          </p>
        </section>
      </div>
      <aside class="p2-card">
        <div class="p2-row">
          <h2>내 알림</h2>
          <span class="p2-badge">미읽음 {{ unread }}</span>
        </div>
        <p class="p2-muted">최근 전달된 알림 100건 · 읽음은 후보 해결이나 회수 완료를 뜻하지 않습니다.</p>
        <article
          v-for="notification in notifications"
          :key="notification.id"
          style="border-top: 1px solid var(--uo-line); padding: 16px 0"
        >
          <strong>{{ notification.read_at ? '확인한 후보 알림' : '새 후보 알림' }}</strong>
          <p class="p2-muted">{{ when(notification.delivered_at) }}</p>
          <RouterLink class="p2-link" :to="`/reclaim/targets/${notification.target_id}`"
            >후보 확인 →</RouterLink
          >
          <div class="p2-actions">
            <button
              v-if="!notification.read_at"
              class="p2-btn"
              :disabled="!!reading || !!error"
              @click="markRead(notification)"
            >
              {{ reading === notification.id ? '저장 중…' : '읽음 처리' }}</button
            ><small v-else>읽음 {{ when(notification.read_at) }}</small>
          </div>
        </article>
        <p v-if="overview && !notifications.length" class="p2-muted">전달된 알림이 없습니다.</p>
      </aside>
    </div>
  </Workspace>
</template>
