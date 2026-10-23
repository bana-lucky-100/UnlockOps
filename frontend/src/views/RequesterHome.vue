<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiError, type Platform, type Problem } from '../api'
import { isV2, listMine, submitV2 } from '../lib/data'
import AppShell from '../components/AppShell.vue'
import RequestList from '../components/RequestList.vue'
import { PLATFORMS, PLATFORM_ORDER, PLATFORM_ORDER_V2 } from '../lib/platforms'
import { guessPlatforms } from '../lib/platformGuess'
import { usePolling } from '../lib/polling'
import { groupOf, needsRefresh, type StatusGroup } from '../lib/status'
import { currentUser } from '../session'
import { useProblemSubmission } from '../composables/useProblemSubmission'

const router = useRouter()
const route = useRoute()
const { submitProblem } = useProblemSubmission()
const MAX = 500
// AI는 적힌 이름으로만 자원을 찾는다(이름이 없거나 모호하면 추측하지 않고 담당자 검토로 넘긴다).
// 그래서 예시에도 이름 자리를 꼭 넣는다.
// Phase 2: '막힌 증상'이 아니라 '필요한 권한 + 이유(TF·업무)'를 받는다. 이유가 있어야 판단안이 근거 조항을 찾는다.
const EXAMPLE: Record<Platform, string> = {
  GITHUB: '[저장소 이름] 저장소 쓰기 권한이 필요해요. [TF·업무 이름] 때문에요',
  JIRA: '[프로젝트 키] 프로젝트 권한이 필요해요. [TF·업무 이름] 때문에요',
  SLACK: '[채널 이름] 채널에 들어가야 해요. [TF·업무 이름] 때문에요',
  NOTION: '[페이지 이름] 페이지 편집 권한이 필요해요. [TF·업무 이름] 때문에요',
  SNOWFLAKE: '[웨어하우스 이름] 웨어하우스를 써야 해요. [TF·업무 이름] 분석 때문에요',
  DATABRICKS: '[작업 공간 이름] 노트북 편집 권한이 필요해요. [TF·업무 이름] 때문에요',
  SALESFORCE: '[담당 고객] 조회 권한이 필요해요. [업무 이름] 때문에요',
  DATADOG: '[서비스 이름] 로그 · 대시보드를 봐야 해요. [TF·업무 이름] 때문에요',
  TABLEAU_CLOUD: '[프로젝트 이름] 대시보드를 만들어야 해요. [TF·업무 이름] 때문에요',
  FIGMA: '[파일 · 프로젝트 이름] 파일 편집 권한이 필요해요. [TF·업무 이름] 때문에요',
}
// v2(Phase 2 계정)는 10개 플랫폼, 구 계정은 4개.
const ORDER = computed(() => isV2() ? PLATFORM_ORDER_V2 : PLATFORM_ORDER)

// 요청 1건 = 플랫폼 1개. 화면에서도 한 번에 하나만 고르게 해서 헷갈리지 않게 한다.
const selected = ref<Platform | null>(null)
const contents = ref('')
// 상세의 '이름 넣어 다시 보내기'에서 왔으면 같은 플랫폼 · 이전 문구를 채워 두고, 주소는 깨끗하게 되돌린다.
{
  const qp = String(route.query.platform ?? '') as Platform
  if (qp in PLATFORMS) {
    selected.value = qp
    contents.value = String(route.query.text ?? '').slice(0, 500)
    void router.replace({ query: {} })
  }
}
const sending = ref(false)
const formError = ref('')

const items = ref<Problem[]>([])
const loaded = ref(false)
const loadError = ref('')

const ready = computed(() => !!selected.value && contents.value.trim().length >= 2)
const placeholder = computed(() => selected.value
  ? '예: ' + EXAMPLE[selected.value]
  : '예: 분석용 Snowflake 웨어하우스 이용 권한이 필요해요. 추천 모델 TF 때문에요')
const rows = computed(() => Math.min(4, Math.max(1, Math.ceil(contents.value.length / 40) + contents.value.split('\n').length - 1)))

const counts = computed(() => {
  const c: Record<StatusGroup, number> = { progress: 0, waiting: 0, finished: 0 }
  for (const p of items.value) c[groupOf(p)]++
  return c
})
const steps = computed(() => [
  { key: 'progress' as const, no: '01', name: '판단안 작성 중', desc: 'AI가 규정 근거와 부서 예산 영향을 정리하고 있어요', bg: '#EEF0FF', fg: '#2F3DB8' },
  { key: 'waiting' as const, no: '02', name: '승인 대기', desc: '부서장 → 최종 승인자 순서로 확인하고 있어요', bg: '#FDF0E4', fg: '#9A4A08' },
  { key: 'finished' as const, no: '03', name: '끝난 요청', desc: '완료 · 거절 · 실패 — 결과와 이유를 확인해 주세요', bg: '#E6F4EC', fg: '#1A7340' },
].map(s => ({ ...s, count: counts.value[s.key] })))
// 홈에는 최근 5건만. 전체 · 상태별 목록은 '내 요청' 페이지에서 본다.
const recent = computed(() => items.value.slice(0, 5))

// 플랫폼은 문장에서 찾아 제안하고(하나만 걸리면 자동 선택), 틀리면 직접 고른다. 직접 고른 값은 문장이 바뀌어도 유지한다.
const manual = ref(false)
const pfOpen = ref(false)
// 목록 밖을 누르거나 Esc를 누르면 닫는다.
const pfBtn = ref<HTMLElement | null>(null)
const pfPop = ref<HTMLElement | null>(null)
function closeOutside(e: Event) {
  if (!pfOpen.value) return
  if (e instanceof KeyboardEvent) { if (e.key === 'Escape') pfOpen.value = false; return }
  const t = e.target as Node
  if (!pfBtn.value?.contains(t) && !pfPop.value?.contains(t)) pfOpen.value = false
}
onMounted(() => { document.addEventListener('pointerdown', closeOutside); document.addEventListener('keydown', closeOutside) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', closeOutside); document.removeEventListener('keydown', closeOutside) })
const guessLabels = computed(() => guesses.value.map(g => PLATFORMS[g].label).join(' · '))
const guesses = computed(() => guessPlatforms(contents.value).filter(p => ORDER.value.includes(p)))
watch(guesses, g => {
  if (manual.value) return
  selected.value = g.length === 1 ? g[0] : null
})
function pick(p: string) {
  formError.value = ''
  selected.value = (p || null) as Platform | null
  manual.value = !!p
}

async function load() {
  try {
    items.value = await listMine()
    loadError.value = ''
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 401 ? '로그인이 끝났어요. 다시 로그인해 주세요.' : '요청 목록을 불러오지 못했어요.'
    throw e
  } finally {
    loaded.value = true
  }
  // 아직 끝나지 않은 요청이 있을 때만 계속 조회한다.
  return items.value.some(p => needsRefresh(p))
}
const polling = usePolling(load)

async function send() {
  if (sending.value) return
  formError.value = ''
  if (!selected.value) { formError.value = '어떤 플랫폼 권한인지 문장에 적거나 왼쪽 플랫폼 버튼에서 골라 주세요'; return }
  if (contents.value.trim().length < 2) { formError.value = '필요한 권한과 이유를 2자 이상 적어 주세요'; return }
  sending.value = true
  try {
    const createdId = isV2()
      ? await submitV2(selected.value, contents.value.trim())
      : (await submitProblem({ platform: selected.value, contents: contents.value.trim(), simulateJiraFailure: false }))?.id ?? null
    if (!createdId) return
    // 보낸 요청의 상세로 바로 간다. 진행 단계가 실시간으로 바뀌는 걸 그 자리에서 볼 수 있다.
    // (홈에 '확인하고 있어요' 안내를 남겨 두면, 끝난 뒤에도 아직 확인 중인 것처럼 보였다.)
    contents.value = ''
    selected.value = null
    manual.value = false
    await router.push(`/requests/${createdId}`)
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
    { t: '필요한 권한을 한 문장으로 적으세요', d: '플랫폼 이름(Snowflake, GitHub …)을 쓰면 자동으로 골라요. 틀리면 입력창 왼쪽 버튼에서 바꿔 주세요. 한 번에 한 플랫폼씩 보내요' },
    { t: '자원 이름과 이유를 적어 주세요', d: '저장소 · 프로젝트 · 채널 · 페이지 이름과 쓰는 이유(TF · 업무)를 함께 적어야 AI가 정확히 찾아요. 이름이 없으면 담당자가 확인해요' },
    { t: '두 단계 승인을 기다리세요', d: 'AI가 정리한 규정 근거와 예산 영향을 보고 부서장 → 최종 승인자가 결정해요. 승인되면 자동으로 열려요' },
  ],
  faqs: [
    { q: '여러 플랫폼이 다 막혔어요', a: '권한은 플랫폼마다 따로 승인되고 따로 열려요. 플랫폼마다 한 번씩 보내 주세요.' },
    { q: 'Admin 권한은 왜 안 되나요?', a: '관리자 권한은 보안 위험이 커서 이 서비스에서 자동으로 주지 않아요. 보안팀에 따로 요청해 주세요.' },
    { q: '실패하면 어떻게 되나요?', a: '처음 시도를 포함해 총 3번까지 자동으로 시도해요. 그래도 안 되면 실패로 표시되고 운영 담당자가 확인해요. 다른 플랫폼 요청에는 영향이 없어요.' },
    { q: '거절되면 어디서 이유를 보나요?', a: '승인자가 메모를 남겼다면 요청 상세에 그대로 보여요. 메모가 없으면 승인자에게 문의해 주세요.' },
    { q: '보류는 무슨 뜻인가요?', a: '근거가 부족하거나 부서 잔여 예산이 모자라 바로 승인할 수 없다는 뜻이에요. 요청 상세의 안내대로 부서장에게 예산 증액을 요청한 뒤 다시 보내 주세요.' },
  ],
}
</script>

<template>
  <AppShell :help="help" show-lock>
    <section class="rh-hero">
      <p class="rh-hello">안녕하세요, {{ currentUser?.name }}님</p>
      <h1 class="rh-title">필요한 권한, 근거와<br>예산 영향까지 함께 정리해 드려요</h1>

      <div class="rh-ask">

        <form class="rh-form" novalidate @submit.prevent="send">
          <div class="rh-pf">
            <button ref="pfBtn" type="button" class="rh-pf-btn" :class="{ on: !!selected }" :style="selected ? { '--c': PLATFORMS[selected].color, '--s': PLATFORMS[selected].soft } : {}"
              aria-haspopup="true" :aria-expanded="pfOpen" @click="pfOpen = !pfOpen">
              <svg v-if="selected" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="PLATFORMS[selected].icon" /></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></svg>
              {{ selected ? PLATFORMS[selected].label : '플랫폼 선택' }}
              <svg class="rh-pf-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
            <div v-if="pfOpen" ref="pfPop" class="rh-pf-pop" role="group" aria-label="플랫폼 고르기">
              <button v-for="p in ORDER" :key="p" type="button" class="rh-pf-item" :class="{ hint: guesses.includes(p) }"
                :aria-pressed="selected === p" :style="{ '--c': PLATFORMS[p].color, '--s': PLATFORMS[p].soft }" @click="pick(p); pfOpen = false">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="PLATFORMS[p].icon" /></svg>
                {{ PLATFORMS[p].label }}
              </button>
            </div>
          </div>
          <label for="rh-ask" class="rh-sr">어떤 권한이 왜 필요한가요?</label>
          <textarea id="rh-ask" :value="contents" @input="contents = ($event.target as HTMLTextAreaElement).value" :rows="rows" :maxlength="MAX" :placeholder="placeholder" @keydown="onKey" />
          <span class="rh-count">Enter로 보내기 · {{ contents.length }}/{{ MAX }}</span>
          <button type="submit" class="rh-send" aria-label="요청 보내기" :aria-disabled="!ready || sending" :class="{ on: ready && !sending }">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
        </form>

        <p class="rh-pf-hint" aria-live="polite">
          <template v-if="selected">{{ manual ? '직접 고른 플랫폼이에요' : '문장에서 플랫폼을 찾았어요. 틀리면 왼쪽 버튼을 눌러 바꿔 주세요' }}</template>
          <template v-else-if="guesses.length > 1">{{ guessLabels }} 중 하나를 골라 주세요. 한 번에 하나씩 보내요</template>
          <template v-else>문장에 플랫폼 이름을 쓰면 자동으로 골라요</template>
        </p>
        <p v-if="formError" class="rh-err" role="alert">{{ formError }}</p>
        <p class="rh-tip"><strong>자원 이름과 쓰는 이유(TF · 업무)</strong>를 꼭 적어 주세요. 이름이 없으면 담당자가 직접 확인해야 해서 오래 걸려요</p>
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
        empty="아직 보낸 요청이 없어요. 위에서 플랫폼을 고르고 필요한 권한과 이유를 적어 보세요." @retry="polling.restart()"
      />
    </section>
  </AppShell>
</template>

<style scoped>
.rh-hero { padding: 72px 0 40px; }
.rh-hello { margin: 0 0 12px; font-family: var(--uo-font-en); font-size: 44px; font-weight: 700; letter-spacing: -0.02em; color: var(--uo-primary); }
.rh-title { margin: 0; font-size: 34px; line-height: 1.4; font-weight: 600; letter-spacing: -0.01em; }
.rh-ask { margin-top: 36px; display: flex; flex-direction: column; gap: 12px; }
.rh-chip { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 16px 0 14px; border-radius: 999px; border: 1.5px solid var(--c); background: #fff; color: var(--c); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; transition: background-color .15s ease, color .15s ease; }
.rh-chip[aria-pressed="false"]:hover, .rh-chip[aria-pressed="false"]:focus-visible { background: var(--s); }
.rh-chip[aria-pressed="true"] { background: var(--c); color: #fff; }
.rh-pf { position: relative; align-self: flex-start; padding-top: 4px; }
.rh-pf-btn { display: inline-flex; align-items: center; gap: 7px; height: 40px; padding: 0 12px 0 14px; border-radius: 12px; border: 0; background: var(--uo-primary-soft); color: var(--uo-primary-ink); font: inherit; font-size: 14px; font-weight: 700; white-space: nowrap; cursor: pointer; box-shadow: inset 0 0 0 1px rgba(59,75,216,.18); transition: background-color .15s ease, box-shadow .15s ease; }
.rh-pf-btn:hover, .rh-pf-btn:focus-visible, .rh-pf-btn[aria-expanded="true"] { background: #DCDFFB; box-shadow: inset 0 0 0 1.5px var(--uo-primary); }
.rh-pf-btn.on { background: var(--c); color: #fff; box-shadow: none; }
.rh-pf-btn.on:hover, .rh-pf-btn.on[aria-expanded="true"] { filter: brightness(1.08); }
.rh-pf-chev { margin-left: 2px; transition: transform .15s ease; }
.rh-pf-btn[aria-expanded="true"] .rh-pf-chev { transform: rotate(180deg); }
.rh-pf-pop { position: absolute; z-index: 5; top: 46px; left: 0; width: 520px; max-width: calc(100vw - 48px); display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; padding: 10px; background: #fff; border: 1px solid var(--uo-line); border-radius: 14px; box-shadow: 0 16px 40px rgba(20,26,51,.16); }
.rh-pf-item { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid transparent; border-radius: 10px; background: #fff; color: var(--c); font: inherit; font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; }
.rh-pf-item:hover, .rh-pf-item:focus-visible { background: var(--s); }
.rh-pf-item.hint { border-color: var(--c); }
.rh-pf-item[aria-pressed="true"] { background: var(--c); color: #fff; }
.rh-pf-hint { margin: 0; font-size: 13px; color: var(--uo-muted); }
.rh-form { position: relative; display: flex; align-items: flex-end; gap: 12px; padding: 8px 8px 8px 8px; background: rgba(255,255,255,0.92); border: 1px solid var(--uo-line-strong); border-radius: 16px; box-shadow: 0 8px 30px rgba(59,75,216,0.10); }
.rh-form textarea { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; font: inherit; font-size: 16px; line-height: 1.5; color: var(--uo-ink); padding: 10px 0; resize: none; }
.rh-form:focus-within { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
.rh-count { font-size: 12px; color: var(--uo-muted); white-space: nowrap; padding-bottom: 14px; }
.rh-send { width: 44px; height: 44px; flex: 0 0 44px; border: 0; border-radius: 12px; background: #B4B9CE; color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.rh-send.on { background: var(--uo-gradient); }
.rh-send svg { transition: transform .2s ease; }
.rh-send.on:hover svg { transform: translateX(3px); }
.rh-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.rh-err { margin: 0; font-size: 14px; font-weight: 500; color: var(--uo-bad); background: var(--uo-bad-bg); border-radius: 10px; padding: 10px 14px; }
.rh-tip { margin: 0; font-size: 14px; color: var(--uo-muted); }
.rh-tip strong { color: var(--uo-ink-2); font-weight: 600; }
.rh-mine-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; min-height: 36px; }
.rh-mine-head h2 { margin: 0; font-size: 22px; font-weight: 700; }
.rh-all { text-decoration: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 16px; border-radius: 999px; background: #fff; border: 1px solid #D5D9EA; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; transition: background-color .2s ease, border-color .2s ease, color .2s ease; }
.rh-all svg { transition: transform .2s ease; }
.rh-all:hover, .rh-all:focus-visible { background: var(--uo-primary-soft); border-color: #B9C0E8; color: var(--uo-primary-ink); }
.rh-all:hover svg, .rh-all:focus-visible svg { transform: translateX(3px); }
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
.rh-arr { position: absolute; right: 10px; bottom: 10px; width: 60px; height: 60px; border-radius: 50%; background: #fff; color: var(--fg); border: 1px solid var(--uo-line); box-shadow: 0 4px 14px rgba(20,26,51,0.08); box-sizing: border-box; display: flex; align-items: center; justify-content: center; transition: background-color .25s ease, color .25s ease, border-color .25s ease; }
.rh-arr svg { transition: transform .2s ease; }
/* 카드 전체가 링크지만, 색 변화는 동그라미 화살표에 올렸을 때(또는 키보드 포커스)만. */
.rh-arr:hover svg, .rh-step:focus-visible .rh-arr svg { transform: translate(3px, -3px); }
.rh-arr:hover, .rh-step:focus-visible .rh-arr { background: var(--fg); color: #fff; border-color: var(--fg); }
.rh-recent { margin-top: 16px; }
.rh-en { font-family: var(--uo-font-en); }
@media (max-width: 720px) {
  .rh-hero { padding: 32px 0 28px; }
  .rh-hello { font-size: 30px; }
  .rh-title { font-size: 24px; }
  .rh-count { display: none; }
}
@media (prefers-reduced-motion: reduce) { .rh-chip, .rh-send svg, .rh-arr, .rh-arr svg, .rh-all, .rh-all svg { transition: none; transform: none; } }
</style>
