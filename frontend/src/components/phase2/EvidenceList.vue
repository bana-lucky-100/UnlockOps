<!-- 미연결: #29 Phase 2 테스트용 화면 · 기존 화면으로 합쳐지면서 현재 라우터에서 빠져 있어 앱에 연결된 화면에서는 쓰이지 않음(이 Phase 2 파일들끼리만 서로 참조). 되살릴 때는 src/router.ts 주석 참고. -->
<script setup lang="ts">
import type { PolicyEvidence } from '../../contracts/phase2'
defineProps<{ items?: PolicyEvidence[] | null }>()
</script>
<template>
  <p v-if="!items?.length" class="p2-muted">확인된 정책 근거가 아직 없습니다.</p>
  <details v-for="(item, i) in items" :key="`${item.source_hash}:${item.article}:${i}`">
    <summary>
      {{ item.doc_id }} · {{ item.article }} <small>버전 {{ item.version }}</small>
    </summary>
    <p class="p2-prose">{{ item.text }}</p>
    <small class="p2-id">원문 해시 {{ item.source_hash }}</small>
  </details>
</template>
