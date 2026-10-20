<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError, type ApprovalSummary, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import RequestList from '../components/RequestList.vue'
import { PLATFORMS } from '../lib/platforms'
import { usePolling } from '../lib/polling'
import { ago } from '../lib/time'
import { currentUser } from '../session'

// GET /api/problems(승인자) = approver_id가 나인 최근 100건. 대기 · 최근 결정을 여기서 나눈다.
const items = ref<Problem[]>([])
const summary = ref<ApprovalSummary | null>(null)
const loaded = ref(false)
const loadError = ref('')

const pending = computed(() => items.value
  .filter(p => p.status === 'WAITING_APPROVAL')
  // 오래 기다린 요청부터
  .sort((a, b) => a.updated_at.localeCompare(b.updated_at)))
// 승인이 필요할 때만 approver_id가 정해지므로, 대기를 지난 요청은 내가 결정한 요청이다.
const DECIDED = new Set(['EXECUTING', 'DONE', 'REJECTED', 'FAILED'])
const recent = computed(() => items.value
  .filter(p => DECIDED.has(p.status))
  .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  .slice(0, 5))

const stats = computed(() => [
  { name: '승인', count: summary.value?.approved ?? 0, desc: '이번 주 내가 승인한 요청', bg: '#E6F4EC', fg: '#1A7340' },
  { name: '거절', count: summary.value?.rejected ?? 0, desc: '이번 주 내가 거절한 요청', bg: '#FCE8EA', fg: '#A61E30' },
  { name: '부여 실패', count: summary.value?.failed ?? 0, desc: '승인했지만 총 3회 시도 후 실패 · 운영 담당자가 확인해요', bg: '#FDF0E4', fg: '#9A4A08' },
])

// 고른 요청 id. 목록이 다시 오면 더는 대기가 아닌 요청은 빼서, 처리된 요청이 승인되지 않게 한다.
const selected = ref<string[]>([])
const allOn = computed(() => pending.value.length > 0 && selected.value.length === pending.value.length)
function toggle(id: string) {
  notice.value = null
  cancelConfirm()
  selected.value = selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id]
}
function toggleAll() {
  notice.value = null
  cancelConfirm()
  selected.value = allOn.value ? [] : pending.value.map(p => p.id)
}

async function load() {
  try {
    const [list, sum] = await Promise.all([
      api<Problem[]>('/problems'),
      api<ApprovalSummary>('/approvals/summary'),
    ])
    items.value = list
    summary.value = sum
    loadError.value = ''
    const waiting = new Set(pending.value.map(p => p.id))
    selected.value = selected.value.filter(id => waiting.has(id))
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 401 ? '로그인이 끝났어요. 다시 로그인해 주세요.' : '승인 목록을 불러오지 못했어요.'
    throw e
  } finally {
    loaded.value = true
  }
  // 새 요청이 언제든 올라오므로 계속 조회한다 (탭이 가려지면 쉰다).
  return true
}
const polling = usePolling(load)

// 여러 건 승인: 화면에서만 묶고, API는 요청마다 각자의 plan_hash로 따로 부른다.
const approving = ref(false)
// 근거를 보지 않고 여러 건을 누르는 실수를 막으려고, 한 번 더 확인한 뒤에 승인한다.
const confirming = ref(false)
// 확인 단계에서 보여 줄 실제 승인 대상. 목록 응답에는 자원 이름이 없어서, 고른 요청마다 상세(plan)를 불러온다.
// 승인도 화면에 보여 준 이 계획(plan_hash)으로만 보낸다 — 승인자가 본 대상과 승인되는 대상이 같도록.
interface Target { id: string; platform: Problem['platform']; resource: string; role: string; requester: string; planHash: string }
const targets = ref<Target[]>([])
const checking = ref(false)
const checkError = ref('')
async function askConfirm() {
  if (!selected.value.length || approving.value || checking.value) return
  checking.value = true
  checkError.value = ''
  notice.value = null
  try {
    const details = await Promise.all(selected.value.map(id => api<Problem>(`/problems/${encodeURIComponent(id)}`)))
    const ready = details.filter(d => d.status === 'WAITING_APPROVAL' && d.plan?.resource_key && d.plan_hash)
    targets.value = ready.map(d => ({
      id: d.id, platform: d.platform, resource: d.plan!.resource_key, role: d.requested_role || d.plan!.requested_role,
      requester: d.requester_name, planHash: d.plan_hash!,
    }))
    if (ready.length < details.length) {
      checkError.value = `${details.length - ready.length}건은 그사이 처리됐거나 대상을 확인할 수 없어 빼고 보여 드려요.`
      selected.value = ready.map(d => d.id)
    }
    confirming.value = targets.value.length > 0
  } catch {
    checkError.value = '승인 대상을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  } finally {
    checking.value = false
  }
}
function cancelConfirm() { confirming.value = false; targets.value = []; checkError.value = '' }
const notice = ref<{ tone: 'ok' | 'warn'; text: string } | null>(null)
async function approveSelected() {
  if (approving.value || !targets.value.length) return
  const list = targets.value
  confirming.value = false
  targets.value = []
  checkError.value = ''
  approving.value = true
  notice.value = null
  let ok = 0
  let changed = 0
  let other = 0
  for (const t of list) {
    try {
      await api(`/problems/${encodeURIComponent(t.id)}/decision`, {
        method: 'POST',
        body: JSON.stringify({ approved: true, expectedPlanHash: t.planHash, reason: '' }),
      })
      ok++
    } catch (e) {
      // 409: 이미 처리됐거나 승인 카드(계획)가 바뀜 → 상세에서 다시 확인해야 한다.
      if (e instanceof ApiError && e.status === 409) changed++
      else other++
    }
  }
  selected.value = []
  const failed = changed + other
  notice.value = failed === 0
    ? { tone: 'ok', text: `${ok}건을 승인했어요. 요청마다 따로 부여되고 결과가 기록돼요.` }
    : {
        tone: 'warn',
        text: `${list.length}건 중 ${ok}건을 승인했어요. `
          + (changed ? `${changed}건은 이미 처리됐거나 내용이 바뀌어 승인하지 않았어요. 상세에서 다시 확인해 주세요. ` : '')
          + (other ? `${other}건은 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.` : ''),
      }
  approving.value = false
  polling.restart()
}

const help = {
  // 회사마다 조직 구조(TF · 부서)와 권한 이름이 달라서, 특정 조직에만 맞는 문구는 쓰지 않는다.
  howto: [
    { t: '누가 무엇을 요청했는지 보세요', d: '요청자, 플랫폼, 요청 권한이 승인 카드에 정리돼 있어요' },
    { t: 'AI가 찾은 원인과 근거를 확인하세요', d: '사내 규정에 맞는 최소 권한만 올라와요. 관리자 권한은 자동으로 올라오지 않아요' },
    { t: '거절할 땐 사유를 남겨 주세요', d: '요청자에게 그대로 보여서, 무엇을 바꿔 다시 요청할지 알 수 있어요' },
  ],
  faqs: [
    { q: '여러 건을 한 번에 승인하면요?', a: '선택한 요청마다 따로 승인 기록이 남고, 플랫폼마다 따로 부여돼요. 하나가 실패해도 나머지에는 영향이 없어요.' },
    { q: '승인하면 바로 열리나요?', a: '부여한 뒤 다시 조회해 실제로 열렸는지 확인하고, 그 결과를 요청자에게 보여 줘요.' },
    { q: '승인 메모는 누가 보나요?', a: '요청자에게 그대로 보여요. 메모는 선택이고, 거절 사유는 꼭 남겨야 해요.' },
  ],
}
</script>

<template>
  <AppShell :help="help" show-lock>
    <section class="ah-hero">
      <p class="ah-hello">안녕하세요, {{ currentUser?.name }}님</p>
      <h1 class="ah-title">
        <template v-if="!loaded">승인함을 불러오고 있어요</template>
        <!-- 못 불러왔을 때 '기다리는 요청이 없어요'로 보이면 승인자가 할 일이 없다고 오해한다. -->
        <template v-else-if="loadError && !items.length">승인함을 불러오지 못했어요</template>
        <template v-else-if="pending.length">승인을 기다리는 요청이<br><span>{{ pending.length }}건</span> 있어요</template>
        <template v-else>지금은 기다리는 요청이 없어요</template>
      </h1>
      <p class="ah-lead">AI가 소속 부서와 현재 권한, 사내 규정을 먼저 대조했어요. 근거를 보고 결정만 해 주세요.</p>
    </section>

    <section aria-labelledby="ah-wait-h">
      <h2 id="ah-wait-h" class="ah-h2">승인 대기 <span class="ah-en ah-warn">{{ pending.length }}</span></h2>

      <div v-if="pending.length" class="ah-bar">
        <button type="button" class="ah-check-all" :aria-pressed="allOn" @click="toggleAll">
          <span class="ah-box" :class="{ on: allOn }" aria-hidden="true">{{ allOn ? '✓' : '' }}</span>전체 선택
        </button>
        <div class="ah-bar-right">
          <template v-if="confirming">
            <button type="button" class="ah-cancel" @click="cancelConfirm">취소</button>
            <button type="button" class="ah-bulk on" @click="approveSelected">{{ targets.length }}건 승인</button>
          </template>
          <template v-else>
            <span class="ah-bar-note">선택한 요청마다 따로 승인 기록이 남아요</span>
            <button
              type="button" class="ah-bulk" :class="{ on: selected.length && !approving }"
              :aria-disabled="!selected.length || approving || checking" @click="askConfirm"
            >
              {{ approving ? '승인하는 중…' : checking ? '대상을 확인하는 중…' : selected.length ? `선택한 ${selected.length}건 승인` : '승인할 요청을 고르세요' }}
            </button>
          </template>
        </div>
      </div>

      <section v-if="confirming" class="ah-confirm" aria-labelledby="ah-cf-h" role="region">
        <h3 id="ah-cf-h">이 {{ targets.length }}건을 승인할까요? <span>승인하면 바로 권한이 부여돼요</span></h3>
        <ul>
          <li v-for="t in targets" :key="t.id">
            <span class="ah-tag" :style="{ '--c': PLATFORMS[t.platform].color, '--s': PLATFORMS[t.platform].soft }">{{ PLATFORMS[t.platform].label }}</span>
            <strong class="ah-en">{{ t.resource }}</strong>
            <span class="ah-role">{{ t.role }}</span>
            <span class="ah-cf-who">{{ t.requester }}</span>
          </li>
        </ul>
      </section>
      <p v-if="checkError" class="ah-notice warn" role="status">{{ checkError }}</p>
      <p v-if="notice" class="ah-notice" :class="notice.tone" role="status">{{ notice.text }}</p>

      <div class="ah-list">
        <p v-if="!loaded" class="ah-empty">불러오는 중…</p>
        <div v-else-if="loadError && !items.length" class="ah-empty" role="alert">
          {{ loadError }} <button type="button" class="ah-retry" @click="polling.restart()">다시 불러오기</button>
        </div>
        <p v-else-if="!pending.length" class="ah-empty">기다리는 요청이 없어요</p>
        <article
          v-for="p in pending" :key="p.id" class="ah-req" :class="{ on: selected.includes(p.id) }"
          :style="{ '--c': PLATFORMS[p.platform].color, '--s': PLATFORMS[p.platform].soft }"
        >
          <button
            type="button" class="ah-box" :class="{ on: selected.includes(p.id) }" :aria-pressed="selected.includes(p.id)"
            :aria-label="`${p.requester_name} ${PLATFORMS[p.platform].label} 요청 선택`" @click="toggle(p.id)"
          >{{ selected.includes(p.id) ? '✓' : '' }}</button>
          <div class="ah-req-main">
            <div class="ah-req-meta">
              <span class="ah-tag">{{ PLATFORMS[p.platform].label }}</span>
              <strong>{{ p.requester_name }}</strong>
              <span class="ah-en">{{ p.employee_no }}</span> · {{ ago(p.updated_at) }} 대기
            </div>
            <!-- 목록 응답에는 자원 이름이 없어서 권한만 보여 준다. 자원은 상세(승인 카드)에서 확인한다. -->
            <p class="ah-req-title"><span class="ah-role">{{ p.requested_role || '권한 확인 필요' }}</span> 권한 요청</p>
            <p class="ah-req-quote">“{{ p.contents }}”</p>
          </div>
          <div v-if="p.diagnosis" class="ah-ai">
            <span class="ah-ai-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /></svg>
              AI 진단
            </span>
            <span class="ah-ai-text">{{ p.diagnosis }}</span>
          </div>
          <RouterLink :to="`/requests/${p.id}`" class="ah-open">
            근거 보기<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </RouterLink>
        </article>
      </div>
    </section>

    <section aria-labelledby="ah-week-h" class="ah-week">
      <h2 id="ah-week-h" class="ah-h2">이번 주 내 승인 현황</h2>
      <!-- 부서 정보도 이번 주 숫자라서 현황과 한곳에 모은다. 첫 화면 오른쪽은 요청자 홈처럼 자물쇠 자리. -->
      <p v-if="summary" class="ah-dept">
        <strong>{{ summary.department }}</strong>
        <span>구성원 <b class="ah-en">{{ summary.memberCount }}</b>명</span>
        <span>이번 주 나에게 온 요청 <b class="ah-en">{{ summary.weekRequests }}</b>건</span>
      </p>
      <div class="ah-stats">
        <div v-for="s in stats" :key="s.name" class="ah-stat" :style="{ background: s.bg, '--fg': s.fg }">
          <span class="ah-stat-name">{{ s.name }}</span>
          <span class="ah-stat-count"><b>{{ s.count }}</b>건</span>
          <span class="ah-stat-desc">{{ s.desc }}</span>
        </div>
      </div>

      <RequestList
        class="ah-recent" title="최근 결정" :items="recent" :loaded="loaded" :error="loadError"
        empty="아직 결정한 요청이 없어요." show-requester @retry="polling.restart()"
      />
    </section>
  </AppShell>
</template>

<style scoped>
.ah-hero { padding: 72px 0 40px; }
.ah-hello { margin: 0 0 12px; font-family: var(--uo-font-en); font-size: 44px; font-weight: 700; letter-spacing: -0.02em; color: var(--uo-primary); }
.ah-title { margin: 0; font-size: 34px; line-height: 1.4; font-weight: 600; letter-spacing: -0.01em; }
.ah-title span { color: var(--uo-warn); }
.ah-lead { margin: 16px 0 0; font-size: 16px; line-height: 1.6; color: var(--uo-ink-2); }
.ah-dept { margin: 0 0 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px; padding: 14px 20px; background: #fff; border: 1px solid var(--uo-line); border-radius: 14px; font-size: 14px; color: var(--uo-muted); }
.ah-dept strong { font-size: 15px; color: var(--uo-ink); }
.ah-dept b { font-size: 18px; font-weight: 700; color: var(--uo-ink); margin: 0 2px; }
.ah-h2 { margin: 0 0 16px; font-size: 22px; font-weight: 700; }
.ah-en { font-family: var(--uo-font-en); }
.ah-warn { color: var(--uo-warn); }
.ah-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; padding: 12px 16px; background: #fff; border: 1px solid var(--uo-line); border-radius: 14px; }
.ah-bar-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ah-bar-note { font-size: 13px; color: var(--uo-muted); }
.ah-check-all { display: inline-flex; align-items: center; gap: 10px; min-height: 44px; padding: 0; border: 0; background: none; font: inherit; font-size: 14px; font-weight: 600; color: var(--uo-ink-2); cursor: pointer; }
.ah-box { width: 24px; height: 24px; flex: 0 0 24px; border-radius: 6px; border: 1.5px solid var(--uo-line-strong); background: #fff; color: #fff; font-size: 14px; padding: 0; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; cursor: pointer; }
.ah-box.on { background: var(--uo-primary); border-color: var(--uo-primary); }
/* 체크박스는 24px로 보이되, 누르는 영역은 44px로 넓힌다. */
.ah-req > .ah-box { position: relative; }
.ah-req > .ah-box::after { content: ''; position: absolute; inset: -10px; }
.ah-bulk { height: 44px; padding: 0 18px; border: 0; border-radius: 12px; font: inherit; font-size: 14px; font-weight: 700; color: #fff; background: #B4B9CE; cursor: not-allowed; }
.ah-bulk.on { background: var(--uo-gradient); cursor: pointer; }
.ah-confirm { margin: 0 0 12px; padding: 16px 20px; background: #fff; border: 1.5px solid var(--uo-primary); border-radius: 14px; }
.ah-confirm h3 { margin: 0 0 10px; font-size: 15px; font-weight: 700; }
.ah-confirm h3 span { margin-left: 6px; font-size: 13px; font-weight: 500; color: var(--uo-muted); }
.ah-confirm ul { list-style: none; margin: 0; padding: 0; }
.ah-confirm li { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 0; border-top: 1px solid #EEF0F6; font-size: 15px; }
.ah-confirm li:first-child { border-top: 0; }
.ah-cf-who { margin-left: auto; font-size: 13px; color: var(--uo-muted); }
.ah-cancel { height: 44px; padding: 0 16px; border-radius: 12px; border: 1px solid #D5D9EA; background: #fff; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.ah-notice { margin: 0 0 12px; font-size: 14px; font-weight: 600; border-radius: 12px; padding: 10px 14px; }
.ah-notice.ok { color: var(--uo-ok); background: var(--uo-ok-bg); }
.ah-notice.warn { color: var(--uo-warn); background: var(--uo-warn-bg); }
.ah-list { display: flex; flex-direction: column; gap: 12px; }
.ah-empty { margin: 0; padding: 28px; text-align: center; font-size: 15px; color: var(--uo-muted); background: #fff; border: 1px dashed #D5D9EA; border-radius: 20px; display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap; }
.ah-retry { height: 36px; padding: 0 16px; border-radius: 999px; background: #fff; border: 1px solid #D5D9EA; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.ah-req { position: relative; display: flex; gap: 18px; align-items: center; flex-wrap: wrap; padding: 20px 24px 20px 28px; background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; overflow: hidden; transition: box-shadow .2s ease, border-color .2s ease; }
.ah-req::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background: var(--c); }
.ah-req:hover { border-color: #B9C0E8; box-shadow: 0 10px 30px rgba(59,75,216,0.12); }
.ah-req.on { border-color: #8E99E8; }
.ah-req-main { flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.ah-req-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--uo-muted); }
.ah-req-meta strong { font-size: 14px; color: var(--uo-ink); }
.ah-tag { font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: var(--s); color: var(--c); }
.ah-req-title { margin: 0; font-size: 18px; font-weight: 700; line-height: 1.4; }
.ah-role { color: var(--uo-primary-ink); }
.ah-req-quote { margin: 0; font-size: 14px; line-height: 1.5; color: var(--uo-ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ah-ai { flex: 0 1 300px; min-width: 240px; display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border-radius: 14px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 100%); border: 1px solid #C9CEF5; }
.ah-ai-label { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: var(--uo-primary-ink); }
.ah-ai-text { font-size: 14px; font-weight: 600; color: var(--uo-ink); }
.ah-open { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 8px; height: 44px; padding: 0 18px; border-radius: 14px; background: var(--uo-ink); color: #fff; font-size: 14px; font-weight: 600; text-decoration: none; white-space: nowrap; }
.ah-open svg { transition: transform .2s ease; }
.ah-open:hover svg, .ah-open:focus-visible svg { transform: translateX(3px); }
.ah-week { margin-top: 40px; }
.ah-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.ah-stat { display: flex; flex-direction: column; padding: 26px; border-radius: 20px; min-height: 160px; box-sizing: border-box; }
.ah-stat-name { font-size: 15px; font-weight: 600; color: var(--fg); }
.ah-stat-count { margin-top: 12px; display: flex; align-items: baseline; gap: 4px; font-size: 18px; font-weight: 600; }
.ah-stat-count b { font-family: var(--uo-font-en); font-size: 48px; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
.ah-stat-desc { margin-top: 12px; font-size: 14px; line-height: 1.6; color: var(--uo-ink-2); }
.ah-recent { margin-top: 16px; }
@media (max-width: 720px) {
  .ah-hero { padding: 32px 0 28px; }
  .ah-hello { font-size: 30px; }
  .ah-title { font-size: 24px; }
  .ah-ai { min-width: 0; flex-basis: 100%; }
}
@media (prefers-reduced-motion: reduce) { .ah-req, .ah-open svg { transition: none; transform: none; } }
</style>
