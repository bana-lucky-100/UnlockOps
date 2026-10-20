<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { PLATFORMS } from '../lib/platforms'
import { currentUser } from '../session'

// 3단계(#6)에서 진행 기록 · 상태별 안내 · 2.5초 조회를 붙인다. 지금은 목록에서 들어올 자리만 만든다.
const route = useRoute()
const item = ref<Problem|null>(null)
const error = ref('')
api<Problem>(`/problems/${route.params.id}`)
  .then(p => { item.value = p })
  .catch(e => { error.value = (e as Error).message })
const back = currentUser.value?.role === 'APPROVER' ? '/approvals' : '/'
</script>

<template>
  <AppShell :agent-items="[]" :help="{ howto: [], faqs: [] }">
    <RouterLink :to="back" class="rd-back">← 목록으로</RouterLink>
    <p v-if="error" class="rd-err" role="alert">{{ error }}</p>
    <template v-else-if="item">
      <h1 class="rd-title">{{ PLATFORMS[item.platform].label }} <StatusBadge :status="item.status" /></h1>
      <p class="rd-body">{{ item.contents }}</p>
    </template>
  </AppShell>
</template>

<style scoped>
.rd-back { display: inline-block; margin: 32px 0 16px; color: var(--uo-primary); font-weight: 600; text-decoration: none; }
.rd-title { display: flex; align-items: center; gap: 12px; margin: 0 0 12px; font-size: 26px; }
.rd-body { white-space: pre-line; font-size: 16px; }
.rd-err { color: var(--uo-bad); font-weight: 600; }
</style>
