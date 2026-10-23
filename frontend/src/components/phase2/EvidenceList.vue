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
