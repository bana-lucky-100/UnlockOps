<script setup lang="ts">
import { computed } from 'vue'
import { isInsufficient, usd, type CostImpact } from '../lib/costImpact.ts'

// S-02 판단안의 비용 영향 카드. 승인자가 "이 요청이 부서 예산에서 얼마인지"를 숫자로 바로 보게 한다.
const props = defineProps<{ impact: CostImpact; mock?: boolean }>()

const short = computed(() => isInsufficient(props.impact))
// 막대: 승인 전 잔여 예산 대비 이번 요청이 차지하는 비율.
const ratio = computed(() => {
  const { budget_before: before, monthly_cost: cost } = props.impact
  if (!before || before <= 0) return 100
  return Math.min(100, Math.round((cost / before) * 100))
})
</script>

<template>
  <section class="ci" :class="{ short, none: impact.kind === 'NO_COST' }" aria-labelledby="ci-h">
    <div class="ci-head">
      <h2 id="ci-h">비용 영향</h2>
      <span v-if="mock" class="ci-mock">목업 데이터</span>
    </div>

    <template v-if="impact.kind === 'NO_COST'">
      <p class="ci-big">추가 비용 없음</p>
      <p class="ci-sub">이미 계정이 있어 권한만 바뀌어요. 부서 예산에는 영향이 없어요.</p>
    </template>

    <template v-else>
      <p class="ci-big"><span class="ci-minus">월 −{{ usd(impact.monthly_cost) }}</span></p>
      <p v-if="impact.basis" class="ci-sub">{{ impact.basis }}</p>

      <dl v-if="impact.budget_before !== null" class="ci-flow">
        <div><dt>지금 잔여 예산</dt><dd class="ci-en">{{ usd(impact.budget_before) }}</dd></div>
        <span class="ci-arrow" aria-hidden="true">→</span>
        <div><dt>승인하면</dt><dd class="ci-en" :class="{ neg: short }">{{ impact.budget_after === null ? '–' : usd(impact.budget_after) }}</dd></div>
      </dl>
      <div v-if="impact.budget_before !== null" class="ci-bar" role="img"
        :aria-label="`잔여 예산의 ${ratio}%를 사용`"><span :style="{ width: ratio + '%' }" /></div>
      <p v-if="impact.budget_before !== null && !short" class="ci-pct">이번 요청이 부서 잔여 예산의 <b class="ci-en">{{ ratio }}%</b>를 써요</p>

      <p v-if="short" class="ci-warn" role="note">잔여 예산이 월 비용보다 적어 보류 대상이에요. 부서장에게 예산 증액을 요청해야 해요.</p>
    </template>
  </section>
</template>

<style scoped>
.ci { background: #fff; border: 1px solid var(--uo-line); border-radius: var(--uo-radius-lg); padding: 22px 24px; box-shadow: 0 1px 2px rgba(20,26,51,.04); display: flex; flex-direction: column; gap: 8px; border-left: 6px solid var(--uo-primary); }
.ci.short { border-left-color: var(--uo-review); }
.ci.none { border-left-color: var(--uo-line-strong); }
.ci-head { display: flex; justify-content: space-between; align-items: center; }
.ci-head h2 { margin: 0; font-size: 18px; font-weight: 700; }
.ci-mock { font-size: 12px; font-weight: 700; color: var(--uo-review); background: var(--uo-review-bg); border-radius: 999px; padding: 2px 10px; }
.ci-big { margin: 6px 0 0; font-family: var(--uo-font-en); font-variant-numeric: tabular-nums; font-size: 34px; font-weight: 700; letter-spacing: -0.02em; color: var(--uo-ink); }
.ci.none .ci-big { font-family: var(--uo-font); font-size: 24px; color: var(--uo-muted); }
.ci-minus { color: var(--uo-primary-ink); }
.ci-sub { margin: 0; font-size: 14px; color: var(--uo-muted); }
.ci-flow { margin: 12px 0 0; display: flex; align-items: flex-end; gap: 18px; }
.ci-flow div { display: flex; flex-direction: column; gap: 2px; }
.ci-flow dt { font-size: 13px; color: var(--uo-muted); }
.ci-flow dd { margin: 0; font-size: 24px; font-weight: 700; }
.ci-flow dd.neg { color: var(--uo-bad); }
.ci-arrow { font-size: 20px; color: var(--uo-line-strong); padding-bottom: 4px; }
.ci-en { font-family: var(--uo-font-en); }
.ci-bar { height: 8px; border-radius: 999px; background: var(--uo-primary-soft); overflow: hidden; margin-top: 4px; }
.ci-bar span { display: block; height: 100%; background: var(--uo-gradient); border-radius: 999px; }
.ci.short .ci-bar span { background: var(--uo-review); }
.ci-pct { margin: 2px 0 0; font-size: 13px; color: var(--uo-muted); }
.ci-pct b { color: var(--uo-ink); }
.ci-warn { margin: 6px 0 0; font-size: 14px; font-weight: 600; color: var(--uo-review); background: var(--uo-review-bg); border-radius: 10px; padding: 8px 12px; }
</style>
