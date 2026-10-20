<script setup lang="ts">
import type { Status } from '../api'
import { STATUS } from '../lib/status'

defineProps<{ status: Status }>()
</script>

<template>
  <span class="badge" :class="STATUS[status].tone"><svg v-if="STATUS[status].tone === 'review'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin-right: 4px; vertical-align: -2px"><path d="M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6.5 19a5.5 5.5 0 0 1 11 0" /></svg>{{ STATUS[status].label }}</span>
</template>

<style scoped>
.badge { display: inline-block; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.run  { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.review { background: var(--uo-review-bg); color: var(--uo-review); }
.ok   { background: var(--uo-ok-bg); color: var(--uo-ok); }
.bad  { background: var(--uo-bad-bg); color: var(--uo-bad); }
</style>
