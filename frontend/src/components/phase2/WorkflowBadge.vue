<!-- 미연결: #29 Phase 2 테스트용 화면 · 기존 화면으로 합쳐지면서 현재 라우터에서 빠져 있음(어디에서도 불리지 않음). 되살릴 때는 src/router.ts 주석 참고. -->
<script setup lang="ts">
import type { AccessView, ReclaimRunView } from '../../contracts/phase2'
import { statusLabel } from '../../phase2/presentation'
defineProps<{ value: AccessView | ReclaimRunView }>()
</script>
<template>
  <span class="p2-badge" :data-status="value.status">{{ statusLabel(value) }}</span>
</template>
