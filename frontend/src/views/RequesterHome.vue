<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError, type Platform, type Problem } from '../api'
import AppShell, { type AgentItem } from '../components/AppShell.vue'
import { PLATFORMS, PLATFORM_ORDER } from '../lib/platforms'
import { usePolling } from '../lib/polling'
import { groupOf, isTerminal, STATUS, type StatusGroup } from '../lib/status'
import { shortWhen } from '../lib/time'
import { currentUser } from '../session'

const MAX = 500
const EXAMPLE: Record<Platform, string> = {
  GITHUB: 'payment-core에 git push 하면 권한이 없다고 나와요',
  JIRA: 'Jira 로그인은 되는데 PAY 프로젝트가 목록에 안 떠요',
  SLACK: '#proj-payment 채널이 검색이 안 돼요',
  NOTION: '결제 개편 TF 위키 페이지를 열면 접근 권한이 없다고 떠요',
}

const shell = ref<InstanceType<typeof AppShell>>()
const ask = ref<HTMLTextAreaElement>()
const selected = ref<Platform[]>([])
const contents = ref('')
const sending = ref(false)
const formError = ref('')
const sentNotice = ref('')

const items = ref<Problem[]>([])
const loaded = ref(false)
const loadError = ref('')
const filter = ref<StatusGroup | null>(null)

const ready = computed(() => selected.value.length > 0 && contents.value.trim().length >= 2)
const placeholder = computed(() => selected.value.length
  ? '예: ' + EXAMPLE[selected.value[0]]
  : '무엇이 안 되나요? 플랫폼을 먼저 골라 주세요')
const rows = computed(() => Math.min(4, Math.max(1, Math.ceil(contents.value.length / 40) + contents.value.split('\n').length - 1)))

const counts = computed(() => {
  const c: Record<StatusGroup, number> = { progress: 0, waiting: 0, finished: 0 }
  for (const p of items.value) c[groupOf(p.status)]++
  return c
})
const steps = computed(() => [
  { key: 'progress' as const, no: '01', name: '진단 중', desc: 'AI가 소속 TF · 현재 권한 · 사내 규정을 대조하고 있어요', bg: '#EEF0FF', fg: '#2F3DB8' },
  { key: 'waiting' as const, no: '02', name: '승인 대기', desc: '규정 근거와 함께 승인자에게 올라갔어요', bg: '#FDF0E4', fg: '#9A4A08' },
  { key: 'finished' as const, no: '03', name: '끝난 요청', desc: '완료 · 거절 · 실패 · 담당자 검토 — 결과를 확인해 주세요', bg: '#E6F4EC', fg: '#1A7340' },
].map(s => ({ ...s, count: counts.value[s.key] })))
const visible = computed(() => filter.value ? items.value.filter(p => groupOf(p.status) === filter.value) : items.value)

function toggle(p: Platform) {
  formError.value = ''
  selected.value = selected.value.includes(p) ? selected.value.filter(x => x !== p) : [...selected.value, p]
}

async function load() {
  try {
    items.value = await api<Problem[]>('/problems?mine=true')
    loadError.value = ''
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 401 ? '로그인이 끝났어요. 다시 로그인해 주세요.' : '요청 목록을 불러오지 못했어요.'
    throw e
  } finally {
    loaded.value = true
  }
  // 아직 끝나지 않은 요청이 있을 때만 계속 조회한다.
  return items.value.some(p => !isTerminal(p.status))
}
const polling = usePolling(load)

// 요청 1건 = 플랫폼 1개. 여러 개를 고르면 플랫폼마다 따로 보내고, 일부만 실패해도 성공한 건은 그대로 둔다.
async function send() {
  if (sending.value) return
  formError.value = ''
  sentNotice.value = ''
  if (!selected.value.length) { formError.value = '어디에서 막혔는지 플랫폼을 하나 이상 골라 주세요'; return }
  if (contents.value.trim().length < 2) { formError.value = '증상을 2자 이상 적어 주세요'; return }
  sending.value = true
  const text = contents.value.trim()
  const targets = [...selected.value]
  const results = await Promise.allSettled(targets.map(platform =>
    api<{ id: string }>('/problems', { method: 'POST', body: JSON.stringify({ platform, contents: text }) })))
  sending.value = false

  const failed = targets.filter((_, i) => results[i].status === 'rejected')
  const ok = targets.filter((_, i) => results[i].status === 'fulfilled')
  if (ok.length) {
    sentNotice.value = failed.length
      ? `${ok.map(p => PLATFORMS[p].label).join(' · ')} 요청을 보냈어요.`
      : `요청 ${ok.length}건을 보냈어요. AI가 플랫폼마다 따로 확인해요.`
    contents.value = ''
    filter.value = null
  }
  if (failed.length) {
    const first = results.find(r => r.status === 'rejected') as PromiseRejectedResult
    formError.value = `${failed.map(p => PLATFORMS[p].label).join(' · ')} 요청은 보내지 못했어요. ${(first.reason as Error).message}`
  }
  // 못 보낸 플랫폼만 선택으로 남겨 다시 보내기 쉽게 한다.
  selected.value = failed
  polling.restart()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); void send() }
}

async function focusAsk() { await nextTick(); ask.value?.focus() }
function showProgress() { filter.value = 'progress'; document.getElementById('mine')?.scrollIntoView({ behavior: 'smooth' }) }

const agentItems = computed<AgentItem[]>(() => [
  { label: '진행 중인 요청 보기', sub: `진단 중 ${counts.value.progress} · 승인 대기 ${counts.value.waiting}`, icon: 'M4 6h16M4 12h16M4 18h10', action: showProgress },
  { label: '새로 요청하기', sub: '막힌 곳을 알려주세요', icon: 'M12 5v14M5 12h14', action: focusAsk },
  { label: '도움말', sub: '사용법과 자주 묻는 질문', icon: 'M9.5 9.5a2.5 2.5 0 0 1 4.9.7c0 1.7-2.4 2.1-2.4 3.6M12 17h.01', action: () => shell.value?.openHelp() },
])
const help = {
  howto: [
    { t: '막힌 플랫폼을 고르세요', d: '여러 개 고르면 플랫폼마다 요청이 따로 만들어지고, 각각 승인돼요' },
    { t: '증상을 적어 주세요', d: '저장소 · 프로젝트 이름은 몰라도 AI가 소속 부서 정보로 찾아요' },
    { t: '승인을 기다리세요', d: 'AI가 찾은 원인과 규정 근거가 부서 승인자에게 올라가고, 승인되면 자동으로 열려요' },
  ],
  faqs: [
    { q: '플랫폼을 여러 개 골랐는데 요청이 여러 건이에요', a: '권한은 플랫폼마다 따로 승인되고 따로 열려요. 그래서 요청도 플랫폼마다 하나씩 만들어져요.' },
    { q: 'Admin 권한은 왜 안 되나요?', a: '관리자 권한은 보안 위험이 커서 이 서비스에서 자동으로 주지 않아요. 보안팀에 따로 요청해 주세요.' },
    { q: '실패하면 어떻게 되나요?', a: '처음 시도를 포함해 총 3번까지 자동으로 시도해요. 그래도 안 되면 실패로 표시되고 운영 담당자가 확인해요. 다른 플랫폼 요청에는 영향이 없어요.' },
    { q: '거절되면 어디서 이유를 보나요?', a: '승인자가 메모를 남겼다면 요청 상세에 그대로 보여요. 메모가 없으면 부서 승인자에게 문의해 주세요.' },
  ],
}
</script>

<template>
  <AppShell ref="shell" :agent-items="agentItems" :help="help" show-lock>
    <section class="rh-hero">
      <p class="rh-hello">안녕하세요, {{ currentUser?.name }}님</p>
      <h1 class="rh-title">막힌 권한, 편리하게<br>근거와 함께 열어드려요</h1>

      <div class="rh-ask">
        <fieldset class="rh-chips">
          <legend>어디에서 막혔나요? <span>여러 개 고르면 플랫폼마다 요청이 따로 만들어져요</span></legend>
          <button
            v-for="p in PLATFORM_ORDER" :key="p" type="button" class="rh-chip"
            :aria-pressed="selected.includes(p)"
            :style="{ '--c': PLATFORMS[p].color, '--s': PLATFORMS[p].soft }"
            @click="toggle(p)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="PLATFORMS[p].icon" /></svg>
            {{ selected.includes(p) ? '✓ ' : '' }}{{ PLATFORMS[p].label }}
          </button>
        </fieldset>

        <form class="rh-form" novalidate @submit.prevent="send">
          <label for="rh-ask" class="rh-sr">무엇이 안 되나요?</label>
          <textarea id="rh-ask" ref="ask" v-model="contents" :rows="rows" :maxlength="MAX" :placeholder="placeholder" @keydown="onKey" />
          <span class="rh-count">Enter로 보내기 · {{ contents.length }}/{{ MAX }}</span>
          <button type="submit" class="rh-send" aria-label="요청 보내기" :aria-disabled="!ready || sending" :class="{ on: ready && !sending }">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
        </form>

        <p v-if="sentNotice" class="rh-ok" role="status">{{ sentNotice }}</p>
        <p v-if="formError" class="rh-err" role="alert">{{ formError }}</p>
        <p class="rh-tip">저장소 · 프로젝트 이름은 몰라도 돼요. 잘 찾는 방법: <strong>언제부터 · 어느 화면에서 · 어떤 메시지</strong>가 나오는지</p>
      </div>
    </section>

    <section id="mine" aria-labelledby="rh-mine-h">
      <div class="rh-mine-head">
        <h2 id="rh-mine-h">내 요청</h2>
        <button v-if="filter" type="button" class="rh-all" @click="filter = null">
          전체 보기<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </div>

      <div class="rh-steps">
        <button
          v-for="s in steps" :key="s.key" type="button" class="rh-step"
          :style="{ background: s.bg, '--fg': s.fg }" :aria-pressed="filter === s.key"
          :aria-label="`${s.name} ${s.count}건만 보기`" @click="filter = filter === s.key ? null : s.key"
        >
          <span class="rh-step-name"><span class="rh-en">{{ s.no }}</span>{{ s.name }}</span>
          <span class="rh-step-count"><b>{{ s.count }}</b>건</span>
          <span class="rh-step-desc">{{ s.desc }}</span>
          <span class="rh-cut" aria-hidden="true" /><span class="rh-cut-a" aria-hidden="true" /><span class="rh-cut-b" aria-hidden="true" />
          <span class="rh-arr" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8" /></svg></span>
        </button>
      </div>

      <div class="rh-recent">
        <h3>{{ filter ? steps.find(s => s.key === filter)?.name : '최근 요청' }}</h3>
        <p v-if="!loaded" class="rh-empty">불러오는 중…</p>
        <div v-else-if="loadError && !items.length" class="rh-empty" role="alert">
          {{ loadError }} <button type="button" class="rh-all" @click="polling.restart()">다시 불러오기</button>
        </div>
        <p v-else-if="!items.length" class="rh-empty">아직 보낸 요청이 없어요. 위에서 막힌 플랫폼을 고르고 증상을 적어 보세요.</p>
        <p v-else-if="!visible.length" class="rh-empty">이 상태의 요청이 없어요.</p>
        <RouterLink v-for="p in visible" :key="p.id" :to="`/requests/${p.id}`" class="rh-row">
          <span class="rh-badge" :class="STATUS[p.status].tone">{{ STATUS[p.status].label }}</span>
          <span class="rh-what">
            <span class="rh-row-title">{{ p.contents.split('\n')[0] }}</span>
            <span class="rh-row-sub">{{ PLATFORMS[p.platform].label }}<template v-if="p.requested_role"> · {{ p.requested_role }}</template> · <span class="rh-en">{{ p.id.slice(0, 8) }}</span></span>
          </span>
          <span class="rh-when">{{ shortWhen(p.created_at) }}</span>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#868CA5" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        </RouterLink>
      </div>
    </section>
  </AppShell>
</template>

<style scoped>
.rh-hero { padding: 72px 0 40px; }
.rh-hello { margin: 0 0 12px; font-family: var(--uo-font-en); font-size: 44px; font-weight: 700; letter-spacing: -0.02em; color: var(--uo-primary); }
.rh-title { margin: 0; font-size: 34px; line-height: 1.4; font-weight: 600; letter-spacing: -0.01em; }
.rh-ask { margin-top: 36px; display: flex; flex-direction: column; gap: 12px; }
.rh-chips { border: 0; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.rh-chips legend { margin-bottom: 10px; font-size: 14px; font-weight: 600; color: var(--uo-ink); }
.rh-chips legend span { font-weight: 400; color: var(--uo-muted); }
.rh-chip { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 16px 0 14px; border-radius: 999px; border: 1.5px solid var(--c); background: #fff; color: var(--c); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; transition: background-color .15s ease, color .15s ease; }
.rh-chip[aria-pressed="false"]:hover, .rh-chip[aria-pressed="false"]:focus-visible { background: var(--s); }
.rh-chip[aria-pressed="true"] { background: var(--c); color: #fff; }
.rh-form { display: flex; align-items: flex-end; gap: 12px; padding: 8px 8px 8px 20px; background: rgba(255,255,255,0.92); border: 1px solid var(--uo-line-strong); border-radius: 16px; box-shadow: 0 8px 30px rgba(59,75,216,0.10); }
.rh-form textarea { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; font: inherit; font-size: 16px; line-height: 1.5; color: var(--uo-ink); padding: 10px 0; resize: none; }
.rh-form:focus-within { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
.rh-count { font-size: 12px; color: var(--uo-muted); white-space: nowrap; padding-bottom: 14px; }
.rh-send { width: 44px; height: 44px; flex: 0 0 44px; border: 0; border-radius: 12px; background: #B4B9CE; color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.rh-send.on { background: var(--uo-gradient); }
.rh-send svg { transition: transform .2s ease; }
.rh-send.on:hover svg { transform: translateX(3px); }
.rh-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.rh-err { margin: 0; font-size: 14px; font-weight: 500; color: var(--uo-bad); background: var(--uo-bad-bg); border-radius: 10px; padding: 10px 14px; }
.rh-ok { margin: 0; font-size: 14px; font-weight: 500; color: var(--uo-ok); background: var(--uo-ok-bg); border-radius: 10px; padding: 10px 14px; }
.rh-tip { margin: 0; font-size: 14px; color: var(--uo-muted); }
.rh-tip strong { color: var(--uo-ink-2); font-weight: 600; }
.rh-mine-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; min-height: 36px; }
.rh-mine-head h2 { margin: 0; font-size: 22px; font-weight: 700; }
.rh-all { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 16px; border-radius: 999px; background: #fff; border: 1px solid #D5D9EA; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.rh-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.rh-step { position: relative; display: flex; flex-direction: column; align-items: flex-start; overflow: hidden; padding: 28px 28px 32px; border: 0; border-radius: 20px; color: var(--uo-ink); min-height: 200px; text-align: left; font: inherit; cursor: pointer; }
.rh-step[aria-pressed="true"] { box-shadow: inset 0 0 0 2px var(--fg); }
.rh-step-name { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: var(--fg); }
.rh-step-count { margin-top: 14px; display: flex; align-items: baseline; gap: 4px; font-size: 18px; font-weight: 600; }
.rh-step-count b { font-family: var(--uo-font-en); font-size: 52px; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
.rh-step-desc { margin-top: 14px; max-width: calc(100% - 72px); font-size: 15px; line-height: 1.6; color: var(--uo-ink-2); }
.rh-cut { position: absolute; right: 0; bottom: 0; width: 80px; height: 80px; background: var(--uo-bg); border-top-left-radius: 26px; }
.rh-cut-a { position: absolute; right: 0; bottom: 80px; width: 26px; height: 26px; background: radial-gradient(circle at 0 0, rgba(246,247,252,0) 25.5px, var(--uo-bg) 26px); }
.rh-cut-b { position: absolute; right: 80px; bottom: 0; width: 26px; height: 26px; background: radial-gradient(circle at 0 0, rgba(246,247,252,0) 25.5px, var(--uo-bg) 26px); }
.rh-arr { position: absolute; right: 10px; bottom: 10px; width: 60px; height: 60px; border-radius: 50%; background: #fff; color: var(--fg); border: 1px solid var(--uo-line); box-shadow: 0 4px 14px rgba(20,26,51,0.08); box-sizing: border-box; display: flex; align-items: center; justify-content: center; }
.rh-arr svg { transition: transform .2s ease; }
.rh-step:hover .rh-arr svg, .rh-step:focus-visible .rh-arr svg { transform: translate(3px, -3px); }
.rh-recent { margin-top: 16px; background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; overflow-x: auto; }
.rh-recent h3 { margin: 0; padding: 16px 24px; font-size: 15px; font-weight: 700; color: var(--uo-ink-2); border-bottom: 1px solid #EEF0F6; }
.rh-empty { margin: 0; padding: 24px; color: var(--uo-muted); font-size: 15px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rh-row { display: grid; grid-template-columns: 116px minmax(0, 1fr) auto 18px; align-items: center; gap: 16px; padding: 16px 24px; border-bottom: 1px solid #EEF0F6; text-decoration: none; color: var(--uo-ink); min-width: 600px; }
.rh-row:last-child { border-bottom: 0; }
.rh-row:hover { background: #FAFBFE; }
.rh-badge { justify-self: start; font-size: 13px; font-weight: 700; padding: 5px 12px; border-radius: 999px; white-space: nowrap; }
.rh-badge.run { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rh-badge.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.rh-badge.ok { background: var(--uo-ok-bg); color: var(--uo-ok); }
.rh-badge.bad { background: var(--uo-bad-bg); color: var(--uo-bad); }
.rh-what { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.rh-row-title { font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rh-row-sub { font-size: 13px; color: var(--uo-muted); }
.rh-when { font-size: 14px; color: var(--uo-ink-2); white-space: nowrap; }
.rh-en { font-family: var(--uo-font-en); }
@media (max-width: 720px) {
  .rh-hero { padding: 32px 0 28px; }
  .rh-hello { font-size: 30px; }
  .rh-title { font-size: 24px; }
  .rh-count { display: none; }
}
@media (prefers-reduced-motion: reduce) { .rh-chip, .rh-send svg, .rh-arr svg { transition: none; transform: none; } }
</style>
