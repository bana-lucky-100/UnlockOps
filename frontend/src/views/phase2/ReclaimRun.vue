<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import Workspace from '../../components/phase2/Workspace.vue'
import WorkflowBadge from '../../components/phase2/WorkflowBadge.vue'
import CandidateCard from '../../components/phase2/CandidateCard.vue'
import { phase2, errorMessage, stopPolling } from '../../phase2/api'
import type { ReclaimCandidate, ReclaimRunView } from '../../contracts/phase2'
import { when } from '../../phase2/presentation'
import { usePolling } from '../../lib/polling'
const id = String(useRoute().params.id),
  run = ref<ReclaimRunView | null>(null),
  items = ref<ReclaimCandidate[]>([]),
  error = ref(''),
  filter = ref('all')
const visible = computed(() =>
  items.value.filter(
    (x) =>
      filter.value === 'all' ||
      (filter.value === 'unknown'
        ? x.review_required || !x.candidate_status
        : x.candidate_status === filter.value)
  )
)
const polling = usePolling(async () => {
  try {
    const next = await phase2.run(id)
    const rows = await phase2.items(id)
    run.value = next
    items.value = rows
    error.value = ''
    return ['RECEIVED', 'DIAGNOSING', 'EXECUTING'].includes(next.status)
  } catch (e) {
    error.value = errorMessage(e)
    if (stopPolling(e)) {
      run.value = null
      items.value = []
      return false
    }
    throw e
  }
})
</script>
<template>
  <Workspace
    ><RouterLink class="p2-link" to="/reclaim">← 회수 점검 현황</RouterLink>
    <header class="p2-heading p2-row" style="margin-top: 20px">
      <h1>점검 실행 상세</h1>
      <WorkflowBadge v-if="run" :value="run" />
    </header>
    <div v-if="error" class="p2-alert" role="alert">
      {{ error }} <button class="p2-btn" @click="polling.restart">다시 불러오기</button>
    </div>
    <p v-if="!run && !error" role="status">점검 결과를 확인하고 있습니다.</p>
    <section v-if="run" class="p2-card" style="margin-bottom: 24px">
      <p class="p2-prose" aria-live="polite">{{ run.message }}</p>
      <p>
        전체 조회: {{ run.scan_complete ? '확인됨' : '아직 확인되지 않음' }} · 기준 시각 {{ when(run.as_of) }}
      </p>
      <div class="p2-metrics">
        <span
          >신규 후보<strong>{{ run.scan_complete ? (run.new_candidate_count ?? 0) : '미확정' }}</strong></span
        ><span
          >근거 확인 필요<strong>{{
            run.scan_complete ? (run.needs_review_count ?? 0) : '미확정'
          }}</strong></span
        ><span
          >미완료 알림<strong>{{
            run.scan_complete ? (run.pending_notification_count ?? 0) : '미확정'
          }}</strong></span
        >
      </div>
      <p class="p2-muted">
        점검 완료는 결과 저장과 필수 알림 처리가 끝났다는 뜻입니다. 실제 권한은 회수하지 않습니다.
      </p>
      <small class="p2-id">실행 {{ run.run_id }} · 스냅샷 {{ run.snapshot_id || '미확정' }}</small>
    </section>
    <div class="p2-filter" aria-label="판정 필터">
      <button
        v-for="tab in [
          { id: 'all', label: '전체' },
          { id: 'PENDING_REVIEW', label: '검토 후보' },
          { id: 'RETAINED', label: '유지' },
          { id: 'EXCLUDED', label: '제외' },
          { id: 'unknown', label: '근거 확인 필요' }
        ]"
        :key="tab.id"
        class="p2-btn"
        :aria-pressed="filter === tab.id"
        @click="filter = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>
    <div class="p2-stack">
      <CandidateCard v-for="item in visible" :key="item.assignment_id" :item="item" />
    </div>
    <p v-if="run && !visible.length && !error" class="p2-empty">
      {{
        run.scan_complete
          ? '이 필터에 해당하는 저장 결과가 없습니다.'
          : '아직 저장된 판정이 없습니다. 전체 조회 완료 전에는 후보 없음으로 확정하지 않습니다.'
      }}
    </p>
  </Workspace>
</template>
