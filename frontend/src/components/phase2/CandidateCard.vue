<script setup lang="ts">
import type { ReclaimCandidate } from '../../contracts/phase2'
import { candidateLabel, costLabel, platforms, when } from '../../phase2/presentation'
import EvidenceList from './EvidenceList.vue'
defineProps<{ item: ReclaimCandidate; detail?: boolean; personalRead?: boolean }>()
</script>
<template>
  <article class="p2-card">
    <div class="p2-row">
      <h3>{{ platforms[item.platform] }}</h3>
      <span class="p2-badge" :data-status="item.review_required ? 'MANUAL_REVIEW' : 'WAITING_APPROVAL'">{{
        candidateLabel(item)
      }}</span>
    </div>
    <p class="p2-prose">{{ item.explanation }}</p>
    <p>
      <strong>{{ costLabel(item.cost_impact) }}</strong>
    </p>
    <p class="p2-muted">
      {{ item.cost_impact.basis === 'SYNTHETIC_CONTRACT' ? '시연용 합성 가격 기준 · ' : '' }}실제 회수·예산
      환입 전 검토 금액
    </p>
    <p v-if="item.skip_reason_code === 'ALREADY_NOTIFIED'" class="p2-muted">기존 알림이 있는 후보입니다.</p>
    <p class="p2-muted">
      알림 전달 {{ when(item.notified_at) }}
      <template v-if="personalRead"> · 내 읽음 {{ when(item.read_at) }}</template>
    </p>
    <RouterLink v-if="!detail && item.target_id" :to="`/reclaim/targets/${item.target_id}`" class="p2-link"
      >후보 상세 보기 →</RouterLink
    >
    <details :open="detail">
      <summary>근거와 할당 정보</summary>
      <p class="p2-id">할당 {{ item.assignment_id }}</p>
      <EvidenceList :items="item.policy_evidence" />
      <h4>사실 근거</h4>
      <ul v-if="item.fact_evidence?.length">
        <li v-for="(fact, i) in item.fact_evidence" :key="i">
          {{ fact.source }} · {{ when(fact.observed_at) }}<small class="p2-id">{{ fact.record_id }}</small>
        </li>
      </ul>
      <p v-else class="p2-muted">등록된 사실 근거가 없습니다.</p>
    </details>
  </article>
</template>
