<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { Problem } from '../api'
import { platformOf } from '../lib/platforms'
import { statusOf } from '../lib/status'
import { shortWhen } from '../lib/time'

// 홈의 '최근 요청'과 '내 요청' 페이지가 같은 줄 모양을 쓰도록 목록을 하나로 둔다.
// showRequester: 승인자 화면에서는 누가 요청했는지를 함께 보여 준다.
defineProps<{ title: string; items: Problem[]; loaded: boolean; error?: string; empty: string; showRequester?: boolean }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="rl">
    <h3 class="rl-title">{{ title }}</h3>
    <p v-if="!loaded" class="rl-empty">불러오는 중…</p>
    <div v-else-if="error && !items.length" class="rl-empty" role="alert">
      {{ error }} <button type="button" class="rl-retry" @click="$emit('retry')">다시 불러오기</button>
    </div>
    <p v-else-if="!items.length" class="rl-empty">{{ empty }}</p>
    <RouterLink v-for="p in items" :key="p.id" :to="`/requests/${p.id}`" class="rl-row">
      <span class="rl-badge" :class="statusOf(p).tone"><svg v-if="statusOf(p).tone === 'review'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin-right: 4px; vertical-align: -2px"><path d="M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6.5 19a5.5 5.5 0 0 1 11 0" /></svg>{{ statusOf(p).label }}</span>
      <span class="rl-what">
        <span class="rl-row-title">{{ p.contents.split('\n')[0] }}</span>
        <span class="rl-sub"><template v-if="showRequester">{{ p.requester_name }} · </template>{{ platformOf(p.platform).label }}<template v-if="p.requested_role"> · {{ p.requested_role }}</template><span class="rl-en"> · {{ p.id.slice(0, 8) }}</span></span>
      </span>
      <span class="rl-when">{{ shortWhen(p.created_at) }}</span>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#868CA5" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
    </RouterLink>
  </div>
</template>

<style scoped>
.rl { background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; overflow-x: auto; }
.rl-title { margin: 0; padding: 16px 24px; font-size: 15px; font-weight: 700; color: var(--uo-ink-2); border-bottom: 1px solid #EEF0F6; }
.rl-empty { margin: 0; padding: 24px; color: var(--uo-muted); font-size: 15px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rl-retry { height: 36px; padding: 0 16px; border-radius: 999px; background: #fff; border: 1px solid #D5D9EA; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.rl-row { display: grid; grid-template-columns: 116px minmax(0, 1fr) auto 18px; align-items: center; gap: 16px; padding: 16px 24px; border-bottom: 1px solid #EEF0F6; text-decoration: none; color: var(--uo-ink); min-width: 600px; }
.rl-row:last-child { border-bottom: 0; }
.rl-row { transition: background-color .2s ease; }
.rl-row svg { transition: transform .2s ease; }
.rl-row:hover { background: #FAFBFE; }
.rl-row:hover > svg { transform: translateX(3px); }
@media (max-width: 720px) {
  /* 휴대폰: 가로 스크롤 대신 두 줄. 윗줄 = 상태 · 시간, 아랫줄 = 요청 제목(줄임표). */
  .rl-row { min-width: 0; grid-template-columns: auto minmax(0, 1fr) 16px; grid-template-areas: "badge when arrow" "what what arrow"; row-gap: 8px; gap: 8px 12px; padding: 14px 16px; }
  .rl-badge { grid-area: badge; justify-self: start; }
  .rl-when { grid-area: when; justify-self: end; }
  .rl-what { grid-area: what; }
  .rl-row > svg { grid-area: arrow; }
  .rl-sub .rl-en { display: none; }
}
@media (prefers-reduced-motion: reduce) { .rl-row, .rl-row svg { transition: none; transform: none; } }
.rl-badge { justify-self: start; font-size: 13px; font-weight: 700; padding: 5px 12px; border-radius: 999px; white-space: nowrap; }
.rl-badge.run { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rl-badge.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.rl-badge.review { background: var(--uo-review-bg); color: var(--uo-review); }
.rl-badge.ok { background: var(--uo-ok-bg); color: var(--uo-ok); }
.rl-badge.bad { background: var(--uo-bad-bg); color: var(--uo-bad); }
.rl-what { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.rl-row-title { font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rl-sub { font-size: 13px; color: var(--uo-muted); }
.rl-when { font-size: 14px; color: var(--uo-ink-2); white-space: nowrap; }
.rl-en { font-family: var(--uo-font-en); }
</style>
