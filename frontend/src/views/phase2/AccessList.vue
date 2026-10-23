<script setup lang="ts">
import { computed, ref } from 'vue'
import Workspace from '../../components/phase2/Workspace.vue'
import WorkflowBadge from '../../components/phase2/WorkflowBadge.vue'
import { phase2, errorMessage, stopPolling, type AccessSummary } from '../../phase2/api'
import { canDecide, platforms, when } from '../../phase2/presentation'
import { currentUser } from '../../session'
import { usePolling } from '../../lib/polling'
const items = ref<AccessSummary[]>([]),
  error = ref(''),
  loaded = ref(false)
const filter = ref(currentUser.value?.role === 'APPROVER' ? 'waiting' : 'mine')
const visible = computed(() =>
  items.value.filter((x) =>
    filter.value === 'waiting'
      ? canDecide(x.workflow, currentUser.value?.id)
      : filter.value === 'mine'
        ? x.requester_id === currentUser.value?.id
        : true
  )
)
const polling = usePolling(async () => {
  try {
    items.value = await phase2.summaries()
    error.value = ''
    loaded.value = true
    return true
  } catch (e) {
    error.value = errorMessage(e)
    if (stopPolling(e)) {
      items.value = []
      return false
    }
    throw e
  }
})
</script>
<template>
  <Workspace>
    <header class="p2-heading p2-row">
      <div>
        <h1>권한 요청·승인</h1>
        <p class="p2-muted">담당 요청의 근거와 승인 순서를 확인하세요. 최근 100건을 표시합니다.</p>
      </div>
      <RouterLink class="p2-btn primary" to="/access/new">새 요청 작성</RouterLink>
    </header>
    <div v-if="error" class="p2-alert" role="alert">
      {{ error }} <button class="p2-btn" @click="polling.restart">다시 불러오기</button>
    </div>
    <div class="p2-filter" aria-label="요청 필터">
      <button
        v-for="tab in [
          { id: 'mine', label: '내 요청' },
          { id: 'waiting', label: '내 승인 차례' },
          { id: 'all', label: '조회 가능한 전체' }
        ]"
        :key="tab.id"
        class="p2-btn"
        :aria-pressed="filter === tab.id"
        @click="filter = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>
    <p v-if="!loaded && !error" role="status">요청을 불러오는 중입니다.</p>
    <div class="p2-stack">
      <RouterLink
        v-for="item in visible"
        :key="item.workflow.problem_id"
        class="p2-card"
        :to="`/access/${item.workflow.problem_id}`"
      >
        <div class="p2-row">
          <strong>{{ platforms[item.platform] }} · {{ item.requester_name }}</strong
          ><WorkflowBadge :value="item.workflow" />
        </div>
        <p class="p2-prose">{{ item.contents }}</p>
        <p class="p2-muted">{{ item.workflow.message }}</p>
        <small
          >{{ when(item.created_at)
          }}<template v-if="item.workflow.total_steps">
            · 승인 {{ item.workflow.approval_steps?.filter((s) => s.status === 'APPROVED').length }} /
            {{ item.workflow.total_steps }}</template
          ></small
        >
      </RouterLink>
    </div>
    <p v-if="loaded && !visible.length && !error" class="p2-empty">해당하는 요청이 없습니다.</p>
  </Workspace>
</template>
