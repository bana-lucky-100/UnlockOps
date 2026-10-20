<script setup lang="ts">
import type { Stage, StageKind } from '../lib/requestView'

defineProps<{ stages: Stage[]; summary: string }>()

// 끝난 단계는 열린 자물쇠, 남은 단계는 잠긴 자물쇠 (브랜드 심볼과 같은 모양)
const BODY = 'M7 11h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2z'
const SHACKLE: Record<StageKind, string> = {
  done: 'M7 11V8a5 5 0 0 1 9.6-1.9', cur: 'M8 11V8a4 4 0 0 1 8 0v3', todo: 'M8 11V8a4 4 0 0 1 8 0v3',
  review: 'M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6.5 19a5.5 5.5 0 0 1 11 0', fail: 'M8 8l8 8M16 8l-8 8',
}
const SR: Record<StageKind, string> = { done: '완료', cur: '진행 중', todo: '대기', review: '담당자 확인 중', fail: '실패' }
</script>

<template>
  <section class="sb" aria-label="진행 단계">
    <p :key="summary" class="sb-sum">{{ summary }}</p>
    <ol class="sb-list">
      <li v-for="(g, i) in stages" :key="g.label" class="sb-step" :class="g.kind" :style="{ '--d': `${i * 80}ms` }">
        <span class="sb-bar" aria-hidden="true"><span v-if="g.kind === 'cur'" class="sb-flow" /></span>
        <span class="sb-name">
          <span class="sb-dot" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="overflow: visible">
              <path :d="SHACKLE[g.kind]" class="sb-shackle" />
              <path v-if="g.kind === 'done' || g.kind === 'cur' || g.kind === 'todo'" :d="BODY" />
            </svg>
          </span>
          {{ g.label }}<span class="sb-sr"> · {{ SR[g.kind] }}</span>
        </span>
        <span class="sb-sub">{{ g.sub }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.sb { background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; padding: 24px 28px; margin-bottom: 24px; }
.sb-sum { margin: 0 0 22px; font-size: 19px; font-weight: 600; line-height: 1.5; animation: sb-in .4s ease both; }
.sb-list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.sb-step { display: flex; flex-direction: column; gap: 10px; min-width: 0; --bar: #E4E7F2; --dbg: #F0F1F5; --dfg: #4A5068; --fg: var(--uo-muted); --w: 500; }
.sb-step.done { --bar: #3B4BD8; --dbg: #3B4BD8; --dfg: #fff; --fg: var(--uo-ink); --w: 600; }
.sb-step.cur { --bar: linear-gradient(90deg, #3B4BD8, #7A5CF0); --dbg: #EEF0FF; --dfg: #2F3DB8; --fg: #2F3DB8; --w: 700; }
.sb-step.review { --bar: #D9730D; --dbg: #FDF0E4; --dfg: #9A4A08; --fg: #9A4A08; --w: 700; }
.sb-step.fail { --bar: #C6283A; --dbg: #FCE8EA; --dfg: #A61E30; --fg: #A61E30; --w: 700; }
.sb-bar { position: relative; overflow: hidden; height: 6px; border-radius: 999px; background: var(--bar); }
.sb-flow { position: absolute; top: 0; bottom: 0; left: 0; width: 35%; background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.75), rgba(255,255,255,0)); animation: sb-flow 1.6s ease-in-out infinite; }
.sb-name { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: var(--w); color: var(--fg); }
.sb-dot { width: 28px; height: 28px; flex: 0 0 28px; border-radius: 50%; background: var(--dbg); color: var(--dfg); display: inline-flex; align-items: center; justify-content: center; }
.done .sb-dot { animation: sb-dot .35s cubic-bezier(.34,1.56,.64,1) var(--d) both; }
.done .sb-shackle { transform-box: fill-box; transform-origin: 0% 100%; animation: sb-sh .45s cubic-bezier(.34,1.56,.64,1) calc(var(--d) + 120ms) both; }
.sb-sub { font-size: 13px; color: var(--uo-muted); padding-left: 36px; min-height: 1em; }
.sb-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@keyframes sb-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes sb-flow { from { transform: translateX(-120%); } to { transform: translateX(320%); } }
@keyframes sb-dot { from { background: #F0F1F5; color: #4A5068; transform: scale(.85); } 60% { transform: scale(1.08); } to { transform: scale(1); } }
@keyframes sb-sh { 0% { transform: translateY(3px); } 55% { transform: translateY(-2px) rotate(-14deg); } 100% { transform: none; } }
@media (max-width: 720px) {
  .sb { padding: 20px; }
  .sb-list { grid-template-columns: 1fr; gap: 14px; }
  .sb-step { flex-direction: row; align-items: center; flex-wrap: wrap; gap: 4px 10px; }
  .sb-bar { display: none; }
  .sb-sub { padding-left: 0; }
}
@media (prefers-reduced-motion: reduce) { .sb-sum, .sb-flow, .done .sb-dot, .done .sb-shackle { animation: none; } }
</style>
