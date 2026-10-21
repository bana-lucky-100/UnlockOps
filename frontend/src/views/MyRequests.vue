<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, ApiError, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import RequestList from '../components/RequestList.vue'
import { usePolling } from '../lib/polling'
import { groupOf, needsRefresh, type StatusGroup } from '../lib/status'

const route = useRoute()
const router = useRouter()
const TABS: { key: StatusGroup | null; name: string }[] = [
  { key: null, name: '전체' },
  { key: 'progress', name: '진단 중' },
  { key: 'waiting', name: '확인 대기' },
  { key: 'finished', name: '끝난 요청' },
]
// 고른 탭은 주소(?group=)에 남겨서 새로고침 · 뒤로 가기에도 유지한다.
const group = computed<StatusGroup | null>(() => {
  const g = route.query.group
  return g === 'progress' || g === 'waiting' || g === 'finished' ? g : null
})
function select(key: StatusGroup | null) {
  void router.replace({ query: key ? { group: key } : {} })
}

const items = ref<Problem[]>([])
const loaded = ref(false)
const error = ref('')
async function load() {
  try {
    items.value = await api<Problem[]>('/problems?mine=true')
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 401 ? '로그인이 끝났어요. 다시 로그인해 주세요.' : '요청 목록을 불러오지 못했어요.'
    throw e
  } finally {
    loaded.value = true
  }
  return items.value.some(p => needsRefresh(p))
}
const polling = usePolling(load)

const count = (key: StatusGroup | null) => key ? items.value.filter(p => groupOf(p) === key).length : items.value.length
const visible = computed(() => group.value ? items.value.filter(p => groupOf(p) === group.value) : items.value)
const current = computed(() => TABS.find(t => t.key === group.value)!)

const help = {
  howto: [
    { t: '탭으로 걸러 보세요', d: '진단 중 · 확인 대기(승인 대기 · 담당자 검토) · 끝난 요청으로 나눠 볼 수 있어요' },
    { t: '줄을 누르면 상세가 열려요', d: '진행 단계와 다음에 할 일을 확인할 수 있어요' },
  ],
  faqs: [],
}
</script>

<template>
  <AppShell :help="help">
    <div class="mr-top">
      <RouterLink to="/" class="mr-back">← 홈으로</RouterLink>
      <h1>내 요청</h1>
    </div>

    <div class="mr-tabs" role="tablist" aria-label="상태로 걸러 보기">
      <button
        v-for="t in TABS" :key="t.name" type="button" role="tab" class="mr-tab"
        :aria-selected="group === t.key" @click="select(t.key)"
      >
        {{ t.name }} <span class="mr-count">{{ count(t.key) }}</span>
      </button>
    </div>

    <RequestList
      :title="current.name === '전체' ? '전체 요청' : current.name"
      :items="visible" :loaded="loaded" :error="error"
      :empty="items.length ? '이 상태의 요청이 없어요.' : '아직 보낸 요청이 없어요. 홈에서 막힌 플랫폼을 고르고 증상을 적어 보세요.'"
      @retry="polling.restart()"
    />
  </AppShell>
</template>

<style scoped>
.mr-top { margin: 32px 0 20px; }
.mr-back { font-size: 14px; font-weight: 600; color: var(--uo-primary); text-decoration: none; }
.mr-top h1 { margin: 10px 0 0; font-size: 30px; font-weight: 700; letter-spacing: -0.01em; }
.mr-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.mr-tab { display: inline-flex; align-items: center; gap: 8px; min-height: 40px; padding: 0 16px; border-radius: 999px; border: 1px solid #D5D9EA; background: #fff; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.mr-tab { transition: background-color .2s ease, border-color .2s ease, color .2s ease; }
.mr-tab[aria-selected="false"]:hover { background: var(--uo-primary-soft); border-color: #B9C0E8; color: var(--uo-primary-ink); }
.mr-tab[aria-selected="true"] { background: var(--uo-ink); border-color: var(--uo-ink); color: #fff; }
.mr-count { font-family: var(--uo-font-en); font-size: 13px; opacity: .8; }
@media (prefers-reduced-motion: reduce) { .mr-tab { transition: none; } }
</style>
