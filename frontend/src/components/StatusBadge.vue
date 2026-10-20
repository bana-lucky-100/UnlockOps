<script setup lang="ts">
import type { Status } from '../api'
import { STATUS } from '../lib/status'

defineProps<{ status: Status }>()
</script>

<template>
  <span class="badge" :class="STATUS[status].tone">{{ STATUS[status].label }}</span>
</template>

<style scoped>
.badge { display: inline-block; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.run  { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.ok   { background: var(--uo-ok-bg); color: var(--uo-ok); }
.bad  { background: var(--uo-bad-bg); color: var(--uo-bad); }
</style>
