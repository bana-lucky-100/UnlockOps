<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError, type Platform, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import RequestList from '../components/RequestList.vue'
import { PLATFORMS, PLATFORM_ORDER } from '../lib/platforms'
import { usePolling } from '../lib/polling'
import { groupOf, isTerminal, type StatusGroup } from '../lib/status'
import { currentUser } from '../session'

const MAX = 500
const EXAMPLE: Record<Platform, string> = {
  GITHUB: '저장소에 push하면 권한이 없다고 나와요',
  JIRA: '로그인은 되는데 팀 프로젝트가 목록에 안 보여요',
  SLACK: '팀 채널이 검색되지 않아요',
  NOTION: '팀 위키 페이지를 열면 접근 권한이 없다고 나와요',
}

// 요청 1건 = 플랫폼 1개. 화면에서도 한 번에 하나만 고르게 해서 헷갈리지 않게 한다.
const selected = ref<Platform | null>(null)
const contents = ref('')
const sending = ref(false)
const formError = ref('')
const sentNotice = ref('')

const items = ref<Problem[]>([])
const loaded = ref(false)
const loadError = ref('')

const ready = computed(() => !!selected.value && contents.value.trim().length >= 2)
const placeholder = computed(() => selected.value
  ? '예: ' + EXAMPLE[selected.value]
  : '무엇이 안 되나요? 플랫폼을 먼저 골라 주세요')
const rows = computed(() => Math.min(4, Math.max(1, Math.ceil(contents.value.length / 40) + contents.value.split('\n').length - 1)))

const counts = computed(() => {
  const c: Record<StatusGroup, number> = { progress: 0, waiting: 0, finished: 0 }
  for (const p of items.value) c[groupOf(p.status)]++
  return c
})
const steps = computed(() => [
  { key: 'progress' as const, no: '01', name: '진단 중', desc: 'AI가 소속 · 현재 권한 · 사내 규정을 대조하고 있어요', bg: '#EEF0FF', fg: '#2F3DB8' },
  { key: 'waiting' as const, no: '02', name: '확인 대기', desc: '승인자나 담당자가 확인하고 있어요', bg: '#FDF0E4', fg: '#9A4A08' },
  { key: 'finished' as const, no: '03', name: '끝난 요청', desc: '완료 · 거절 · 실패 — 결과를 확인해 주세요', bg: '#E6F4EC', fg: '#1A7340' },
].map(s => ({ ...s, count: counts.value[s.key] })))
// 홈에는 최근 5건만. 전체 · 상태별 목록은 '내 요청' 페이지에서 본다.
const recent = computed(() => items.value.slice(0, 5))

function toggle(p: Platform) {
  formError.value = ''
  selected.value = selected.value === p ? null : p
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

async function send() {
  if (sending.value) return
  formError.value = ''
  sentNotice.value = ''
  if (!selected.value) { formError.value = '어디에서 막혔는지 플랫폼을 골라 주세요'; return }
  if (contents.value.trim().length < 2) { formError.value = '증상을 2자 이상 적어 주세요'; return }
  sending.value = true
  try {
    await api<{ id: string }>('/problems', { method: 'POST', body: JSON.stringify({ platform: selected.value, contents: contents.value.trim() }) })
    sentNotice.value = `${PLATFORMS[selected.value].label} 요청을 보냈어요. AI가 확인하고 있어요.`
    contents.value = ''
    selected.value = null
    polling.restart()
  } catch (e) {
    // 실패하면 입력은 그대로 두고 다시 보낼 수 있게 한다.
    formError.value = `요청을 보내지 못했어요. ${(e as Error).message}`
  } finally {
    sending.value = false
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); void send() }
}

const help = {
  howto: [
    { t: '막힌 플랫폼을 고르세요', d: '한 번에 하나씩 보내요. 다른 플랫폼도 막혔다면 이어서 한 번 더 보내 주세요' },
    { t: '증상을 적어 주세요', d: '저장소 · 프로젝트 이름은 몰라도 AI가 소속 부서 정보로 찾아요' },
    { t: '승인을 기다리세요', d: 'AI가 찾은 원인과 규정 근거가 승인자에게 올라가고, 승인되면 자동으로 열려요' },
  ],
  faqs: [
    { q: '여러 플랫폼이 다 막혔어요', a: '권한은 플랫폼마다 따로 승인되고 따로 열려요. 플랫폼마다 한 번씩 보내 주세요.' },
    { q: 'Admin 권한은 왜 안 되나요?', a: '관리자 권한은 보안 위험이 커서 이 서비스에서 자동으로 주지 않아요. 보안팀에 따로 요청해 주세요.' },
    { q: '실패하면 어떻게 되나요?', a: '처음 시도를 포함해 총 3번까지 자동으로 시도해요. 그래도 안 되면 실패로 표시되고 운영 담당자가 확인해요. 다른 플랫폼 요청에는 영향이 없어요.' },
    { q: '거절되면 어디서 이유를 보나요?', a: '승인자가 메모를 남겼다면 요청 상세에 그대로 보여요. 메모가 없으면 승인자에게 문의해 주세요.' },
  ],
}
</script>

<template>
  <AppShell :help="help" show-lock>
    <section class="rh-hero">
      <p class="rh-hello">안녕하세요, {{ currentUser?.name }}님</p>
      <h1 class="rh-title">막힌 권한, 편리하게<br>근거와 함께 열어드려요</h1>

      <div class="rh-ask">
        <fieldset class="rh-chips">
          <legend>어디에서 막혔나요? <span>하나만 골라 주세요</span></legend>
          <button
            v-for="p in PLATFORM_ORDER" :key="p" type="button" class="rh-chip"
            :aria-pressed="selected === p"
            :style="{ '--c': PLATFORMS[p].color, '--s': PLATFORMS[p].soft }"
            @click="toggle(p)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="PLATFORMS[p].icon" /></svg>
            {{ selected === p ? '✓ ' : '' }}{{ PLATFORMS[p].label }}
          </button>
        </fieldset>

        <form class="rh-form" novalidate @submit.prevent="send">
          <label for="rh-ask" class="rh-sr">무엇이 안 되나요?</label>
          <textarea id="rh-ask" v-model="contents" :rows="rows" :maxlength="MAX" :placeholder="placeholder" @keydown="onKey" />
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

    <section aria-labelledby="rh-mine-h">
      <div class="rh-mine-head">
        <h2 id="rh-mine-h">내 요청</h2>
        <RouterLink to="/requests" class="rh-all">
          전체 보기<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </RouterLink>
      </div>

      <div class="rh-steps">
        <RouterLink
          v-for="s in steps" :key="s.key" :to="{ path: '/requests', query: { group: s.key } }" class="rh-step"
          :style="{ background: s.bg, '--fg': s.fg }" :aria-label="`${s.name} ${s.count}건 보기`"
        >
          <span class="rh-step-name"><span class="rh-en">{{ s.no }}</span>{{ s.name }}</span>
          <span class="rh-step-count"><b>{{ s.count }}</b>건</span>
          <span class="rh-step-desc">{{ s.desc }}</span>
          <span class="rh-cut" aria-hidden="true" /><span class="rh-cut-a" aria-hidden="true" /><span class="rh-cut-b" aria-hidden="true" />
          <span class="rh-arr" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8" /></svg></span>
        </RouterLink>
      </div>

      <RequestList
        class="rh-recent" title="최근 요청" :items="recent" :loaded="loaded" :error="loadError"
        empty="아직 보낸 요청이 없어요. 위에서 막힌 플랫폼을 고르고 증상을 적어 보세요." @retry="polling.restart()"
      />
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
.rh-all { text-decoration: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 16px; border-radius: 999px; background: #fff; border: 1px solid #D5D9EA; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.rh-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.rh-step { text-decoration: none; position: relative; display: flex; flex-direction: column; align-items: flex-start; overflow: hidden; padding: 28px 28px 32px; border: 0; border-radius: 20px; color: var(--uo-ink); min-height: 200px; text-align: left; font: inherit; cursor: pointer; }
.rh-step:focus-visible { outline: none; }
.rh-step:focus-visible .rh-arr { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
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
.rh-step:hover .rh-arr { background: var(--fg); color: #fff; border-color: var(--fg); }
.rh-recent { margin-top: 16px; }
.rh-en { font-family: var(--uo-font-en); }
@media (max-width: 720px) {
  .rh-hero { padding: 32px 0 28px; }
  .rh-hello { font-size: 30px; }
  .rh-title { font-size: 24px; }
  .rh-count { display: none; }
}
@media (prefers-reduced-motion: reduce) { .rh-chip, .rh-send svg, .rh-arr svg { transition: none; transform: none; } }
</style>
