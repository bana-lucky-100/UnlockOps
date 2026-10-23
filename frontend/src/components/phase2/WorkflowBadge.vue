<script setup lang="ts">
import type { AccessView, ReclaimRunView } from '../../contracts/phase2'
import { statusLabel } from '../../phase2/presentation'
defineProps<{ value: AccessView | ReclaimRunView }>()
</script>
<template>
  <span class="p2-badge" :data-status="value.status">{{ statusLabel(value) }}</span>
</template>
