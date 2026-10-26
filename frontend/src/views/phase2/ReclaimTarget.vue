<!-- 미연결: #29 Phase 2 테스트용 화면 · 기존 화면으로 합쳐지면서 현재 라우터에서 빠져 있어 앱에 연결된 화면에서는 쓰이지 않음(이 Phase 2 파일들끼리만 서로 참조). 되살릴 때는 src/router.ts 주석 참고. -->
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import Workspace from '../../components/phase2/Workspace.vue'
import CandidateCard from '../../components/phase2/CandidateCard.vue'
import { phase2, errorMessage, stopPolling } from '../../phase2/api'
import type { ReclaimCandidate } from '../../contracts/phase2'
import { usePolling } from '../../lib/polling'
const id = String(useRoute().params.id),
  item = ref<ReclaimCandidate | null>(null),
  error = ref('')
const polling = usePolling(async () => {
  try {
    item.value = await phase2.target(id)
    error.value = ''
    return false
  } catch (e) {
    error.value = errorMessage(e)
    if (stopPolling(e)) {
      item.value = null
      return false
    }
    throw e
  }
})
</script>
<template>
  <Workspace
    ><RouterLink class="p2-link" to="/reclaim">← 회수 점검·알림</RouterLink>
    <header class="p2-heading" style="margin-top: 20px">
      <h1>회수 후보 상세</h1>
      <p class="p2-muted">정책·사실 근거와 예상 비용을 확인하세요.</p>
    </header>
    <div v-if="error" class="p2-alert" role="alert">
      {{ error }} <button class="p2-btn" @click="polling.restart">다시 불러오기</button>
    </div>
    <p v-if="!item && !error" role="status">후보를 불러오는 중입니다.</p>
    <CandidateCard v-if="item" :item="item" personal-read detail
  /></Workspace>
</template>
