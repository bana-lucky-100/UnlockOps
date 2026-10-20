<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import StageBar from '../components/StageBar.vue'
import { PLATFORMS } from '../lib/platforms'
import { usePolling } from '../lib/polling'
import { aiMessageOf, noticeOf, proposalOf, stagesOf, summaryOf } from '../lib/requestView'
import { isTerminal, STATUS } from '../lib/status'
import { shortWhen } from '../lib/time'
import { currentUser } from '../session'

const route = useRoute()
const id = String(route.params.id)
const item = ref<Problem | null>(null)
const error = ref('')
const isRequester = computed(() => currentUser.value?.role !== 'APPROVER')
const back = computed(() => isRequester.value ? '/' : '/approvals')

async function load() {
  try {
    item.value = await api<Problem>(`/problems/${id}`)
    error.value = ''
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    error.value = status === 404 ? '요청을 찾을 수 없어요.'
      : status === 403 ? '이 요청을 볼 권한이 없어요.'
      : status === 401 ? '로그인이 끝났어요. 다시 로그인해 주세요.'
      : '요청을 불러오지 못했어요. 잠시 뒤 다시 시도할게요.'
    if (status === 403 || status === 404) return false
    throw e
  }
  return !isTerminal(item.value.status)
}
usePolling(load)


const p = computed(() => item.value)
const platform = computed(() => p.value ? PLATFORMS[p.value.platform] : null)
const stages = computed(() => p.value ? stagesOf(p.value) : [])
const summary = computed(() => p.value ? summaryOf(p.value) : '')
const aiMessage = computed(() => p.value ? aiMessageOf(p.value) : null)
const proposal = computed(() => p.value && platform.value ? proposalOf(p.value, platform.value.label) : null)
const notice = computed(() => p.value ? noticeOf(p.value) : null)
const events = computed(() => (p.value?.events ?? [])
  .map(e => ({ at: e.created_at, text: typeof e.payload?.message === 'string' ? e.payload.message : '' }))
  .filter(e => e.text))
const perm = computed(() => {
  const x = p.value
  if (!x?.requested_role) return null
  const map: Partial<Record<Problem['status'], { label: string; tone: string }>> = {
    WAITING_APPROVAL: { label: '부여 전', tone: 'todo' },
    EXECUTING: { label: '부여 중', tone: 'run' },
    DONE: { label: '✓ 부여 · 확인됨', tone: 'ok' },
    FAILED: { label: '✕ 실패', tone: 'bad' },
  }
  const s = map[x.status]
  if (!s || (x.status === 'DONE' && !x.decided_at)) return null
  return { role: x.requested_role, ...s, title: x.status === 'WAITING_APPROVAL' ? '승인이 필요한 권한' : '부여 결과' }
})
const record = computed(() => {
  const x = p.value
  if (!x) return []
  return [
    { k: '요청 번호', v: x.id, mono: true },
    { k: '요청 시각', v: shortWhen(x.created_at) },
    { k: '마지막 변경', v: shortWhen(x.updated_at) },
    { k: '결정 시각', v: x.decided_at ? shortWhen(x.decided_at) : '아직 없음' },
    { k: '반영 확인', v: x.verification_ok === true ? '✓ 확인됨' : x.verification_ok === false ? '✕ 반영 안 됨' : '아직 없음' },
  ]
})

const help = {
  howto: [
    { t: '진행 단계를 보세요', d: '접수 → AI 진단 → 승인 → 권한 부여 → 반영 확인 순서로 진행돼요. 이 화면을 닫아도 계속 진행돼요' },
    { t: '거절 · 실패 때는 안내를 따르세요', d: '오른쪽 카드에 다음에 할 일이 나와요' },
  ],
  faqs: [
    { q: '거절되면 어디서 이유를 보나요?', a: '승인자가 메모를 남겼다면 이 화면에 그대로 보여요. 메모가 없으면 승인자에게 문의해 주세요.' },
    { q: '실패하면 어떻게 되나요?', a: '처음 시도를 포함해 총 3번까지 자동으로 시도해요. 그래도 안 되면 실패로 표시되고 운영 담당자가 확인해요.' },
  ],
}
</script>

<template>
  <AppShell :help="help">
    <div class="rd-top">
      <div>
        <RouterLink :to="back" class="rd-back">← {{ isRequester ? '홈으로' : '승인함으로' }}</RouterLink>
        <h1 v-if="p && platform">{{ platform.label }}<template v-if="p.requested_role"> · {{ p.requested_role }}</template></h1>
        <p v-if="p" class="rd-meta"><span class="rd-en">{{ p.id.slice(0, 8) }}</span> · {{ p.requester_name }} · {{ shortWhen(p.created_at) }} 요청</p>
      </div>
      <span v-if="p" class="rd-badge" :class="STATUS[p.status].tone">{{ STATUS[p.status].label }}</span>
    </div>

    <p v-if="error && !p" class="rd-state" role="alert">{{ error }} <RouterLink :to="back">돌아가기</RouterLink></p>
    <p v-else-if="!p" class="rd-state">불러오는 중…</p>

    <template v-if="p && platform">
      <p v-if="error" class="rd-warn" role="status">{{ error }}</p>
      <StageBar :stages="stages" :summary="summary" />

      <div class="rd-cols">
        <div class="rd-main">
          <section class="rd-card" aria-labelledby="rd-dg">
            <h2 id="rd-dg">요청 내용과 AI 진단</h2>
            <div class="rd-facts">
              <span>{{ platform.label }}</span>
              <span v-if="p.requested_role">{{ p.requested_role }}</span>
            </div>
            <div class="rd-msgs">
              <p class="rd-msg me">{{ p.contents }}</p>
              <p v-if="aiMessage" class="rd-msg ai">{{ aiMessage }}</p>
            </div>
            <div v-if="proposal" class="rd-proposal">
              <p class="rd-proposal-k">AI 제안</p>
              <p>{{ proposal }}</p>
            </div>
          </section>

          <section v-if="events.length" class="rd-card" aria-labelledby="rd-ev" aria-live="polite">
            <h2 id="rd-ev">진행 기록</h2>
            <ol class="rd-events">
              <li v-for="(e, i) in events" :key="i" :class="{ last: i === events.length - 1 && !isTerminal(p.status) }">
                <span class="rd-mark" aria-hidden="true">{{ i === events.length - 1 && !isTerminal(p.status) ? '' : '✓' }}</span>
                <span class="rd-ev-text">{{ e.text }}</span>
                <span class="rd-ev-at rd-en">{{ shortWhen(e.at) }}</span>
              </li>
            </ol>
          </section>

          <section v-if="perm" class="rd-card" aria-labelledby="rd-pm">
            <h2 id="rd-pm">{{ perm.title }}</h2>
            <article class="rd-perm" :style="{ '--tc': platform.color }">
              <div class="rd-perm-head">
                <span class="rd-ptag" :style="{ background: platform.soft, color: platform.color }">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="platform.icon" /></svg>{{ platform.label }}
                </span>
                <span class="rd-pstate" :class="perm.tone">{{ perm.label }}</span>
              </div>
              <p class="rd-perm-role">요청 권한 <strong>{{ perm.role }}</strong></p>
              <p v-if="p.status === 'FAILED'" class="rd-perm-fail">총 3회 시도했지만 실패 · 운영 담당자가 확인 중</p>
            </article>
          </section>

          <section class="rd-card rd-rec">
            <details>
              <summary>요청 기록 <span>· 시각과 처리 번호</span></summary>
              <dl>
                <template v-for="r in record" :key="r.k"><dt>{{ r.k }}</dt><dd :class="{ 'rd-en': r.mono }">{{ r.v }}</dd></template>
              </dl>
            </details>
          </section>
        </div>

        <aside class="rd-side">
          <section v-if="['RECEIVED', 'DIAGNOSING', 'EXECUTING', 'WAITING_APPROVAL'].includes(p.status)" class="rd-progress">
            <h2>{{ p.status === 'WAITING_APPROVAL' ? '승인을 기다리고 있어요' : p.status === 'EXECUTING' ? '권한을 넣고 있어요' : '진단 중이에요' }}</h2>
            <p>{{ p.status === 'WAITING_APPROVAL' ? '원인과 규정 근거를 정리해 승인자에게 올렸어요. 승인되면 바로 부여돼요.'
              : p.status === 'EXECUTING' ? '부여한 뒤 다시 조회해 반영됐는지 확인해요.'
              : '끝나면 원인을 정리해서 승인자에게 승인을 요청해요.' }}</p>
            <div class="rd-todo"><p class="k">지금 할 일</p><p>없어요. 이 화면을 닫아도 진행되고, 결과는 홈의 '내 요청'에서 볼 수 있어요</p></div>
          </section>

          <section v-if="notice" class="rd-notice" :class="`n-${notice.tone}`" aria-labelledby="rd-nt">
            <h2 id="rd-nt">{{ notice.title }}</h2>
            <div v-if="notice.memo" class="rd-memo"><p class="k">승인자 메모</p><p>{{ notice.memo }}</p></div>
            <div class="rd-todo"><p class="k">다음에 할 일</p><p>{{ notice.next }}</p></div>
            <RouterLink :to="back" class="rd-cta">{{ isRequester ? '내 요청으로 돌아가기' : '승인함으로 돌아가기' }}</RouterLink>
          </section>

          <section v-if="p.status === 'DONE'" class="rd-success">
            <h2>권한이 열렸어요</h2>
            <p>{{ p.decided_at ? `${platform.label}에서 다시 조회해 반영을 확인했어요. 지금 바로 쓸 수 있어요.` : '이미 필요한 권한이 있어요. 그래도 안 되면 로그아웃 후 다시 로그인해 보세요.' }}</p>
          </section>

        </aside>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.rd-top { margin: 28px 0 20px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.rd-back { font-size: 14px; font-weight: 600; color: var(--uo-primary); text-decoration: none; }
.rd-top h1 { margin: 10px 0 0; font-size: 30px; font-weight: 700; letter-spacing: -0.01em; }
.rd-meta { margin: 6px 0 0; font-size: 14px; color: var(--uo-muted); }
.rd-en { font-family: var(--uo-font-en); }
.rd-badge { font-size: 15px; font-weight: 700; padding: 8px 18px; border-radius: 999px; white-space: nowrap; }
.rd-badge.sm { font-size: 12px; padding: 3px 9px; }
.run { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.ok { background: var(--uo-ok-bg); color: var(--uo-ok); }
.bad { background: var(--uo-bad-bg); color: var(--uo-bad); }
.todo { background: #F0F1F5; color: #4A5068; }
.rd-state { background: #fff; border: 1px dashed var(--uo-line-strong); border-radius: 20px; padding: 28px; color: var(--uo-muted); }
.rd-warn { margin: 0 0 12px; color: var(--uo-warn); font-weight: 600; }
.rd-cols { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.rd-main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 20px; }
.rd-side { flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 20px; }
.rd-card { background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; padding: 24px; }
.rd-card h2, .rd-side h2 { margin: 0 0 14px; font-size: 18px; font-weight: 700; }
.rd-facts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.rd-facts span { font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 999px; background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rd-msgs { display: flex; flex-direction: column; gap: 12px; }
.rd-msg { margin: 0; max-width: 82%; padding: 12px 16px; font-size: 15px; line-height: 1.7; white-space: pre-line; }
.rd-msg.me { align-self: flex-end; background: var(--uo-primary); color: #fff; border-radius: 16px 16px 4px 16px; }
.rd-msg.ai { align-self: flex-start; background: #F1F2F8; color: var(--uo-ink); border-radius: 16px 16px 16px 4px; }
.rd-proposal { margin-top: 16px; padding: 14px 16px; border-radius: 14px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 100%); border: 1px solid #C9CEF5; }
.rd-proposal p { margin: 0; font-size: 15px; line-height: 1.65; }
.rd-proposal .rd-proposal-k { margin-bottom: 4px; font-size: 13px; font-weight: 700; color: var(--uo-primary-ink); }
.rd-events { list-style: none; margin: 0; padding: 0; }
.rd-events li { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-bottom: 1px solid #F0F1F6; }
.rd-events li:last-child { border-bottom: 0; }
.rd-mark { width: 24px; height: 24px; flex: 0 0 24px; border-radius: 50%; background: var(--uo-primary); color: #fff; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; }
.last .rd-mark { background: #fff; border: 3px solid #D5DAFB; border-top-color: var(--uo-primary); animation: rd-spin .9s linear infinite; }
.rd-ev-text { flex: 1; font-size: 15px; font-weight: 600; }
.last .rd-ev-text { color: var(--uo-primary-ink); }
.rd-ev-at { font-size: 14px; color: var(--uo-muted); }
.rd-perm { position: relative; overflow: hidden; border: 1px solid var(--uo-line); border-radius: 20px; padding: 20px 20px 16px 26px; }
.rd-perm::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background: var(--tc); }
.rd-perm-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rd-ptag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 5px 10px 5px 8px; border-radius: 999px; }
.rd-pstate { font-size: 13px; font-weight: 700; padding: 5px 10px; border-radius: 999px; }
.rd-perm-role { margin: 14px 0 0; font-size: 16px; color: var(--uo-ink-2); }
.rd-perm-role strong { color: var(--uo-primary-ink); }
.rd-perm-fail { margin: 12px 0 0; font-size: 14px; font-weight: 600; line-height: 1.5; color: var(--uo-bad); background: var(--uo-bad-bg); border-radius: 10px; padding: 8px 12px; }
.rd-rec { padding: 20px 24px; }
.rd-rec details { border: 0; margin: 0; padding: 0; }
.rd-rec summary { font-size: 15px; font-weight: 600; cursor: pointer; }
.rd-rec summary span { font-weight: 400; color: var(--uo-muted); }
.rd-rec dl { margin: 14px 0 0; display: grid; grid-template-columns: 120px minmax(0, 1fr); row-gap: 10px; font-size: 14px; }
.rd-rec dt { color: var(--uo-muted); }
.rd-rec dd { margin: 0; word-break: break-all; }
.rd-progress { border-radius: 24px; padding: 24px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 60%, #F7F3FF 100%); border: 1px solid var(--uo-primary-ink); display: flex; flex-direction: column; gap: 12px; }
.rd-progress h2 { margin: 0; font-size: 20px; color: var(--uo-primary-ink); }
.rd-progress > p { margin: 0; font-size: 15px; line-height: 1.65; }
.rd-todo { background: #fff; border-radius: 12px; padding: 14px 16px; }
.rd-todo p, .rd-memo p { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.55; }
.rd-todo .k, .rd-memo .k { margin-bottom: 4px; font-size: 13px; color: var(--uo-muted); }
.rd-notice { border-radius: 20px; padding: 24px; display: flex; flex-direction: column; gap: 14px; }
.rd-notice.n-bad { background: var(--uo-bad-bg); border: 1px solid #F0C9CF; --nfg: var(--uo-bad); }
.rd-notice.n-warn { background: var(--uo-warn-bg); border: 1px solid #F3D2B3; --nfg: var(--uo-warn); }
.rd-notice h2 { margin: 0; font-size: 20px; line-height: 1.4; color: var(--nfg); }
.rd-memo { background: rgba(255,255,255,0.75); border-radius: 12px; padding: 12px 14px; }
.rd-memo p:last-child { font-weight: 400; }
.rd-cta { height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; color: var(--nfg); background: #fff; border: 1.5px solid var(--nfg); text-decoration: none; }
.rd-success { border-radius: 20px; padding: 24px; background: var(--uo-ok-bg); border: 1px solid #BFE3CC; }
.rd-success h2 { margin: 0 0 10px; font-size: 20px; color: var(--uo-ok); }
.rd-success p { margin: 0; font-size: 15px; line-height: 1.65; }
@keyframes rd-spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) { .rd-top h1 { font-size: 24px; } .rd-msg { max-width: 92%; } }
@media (prefers-reduced-motion: reduce) { .last .rd-mark { animation: none; } }
</style>
