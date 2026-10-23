<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../api'
import AppShell from '../components/AppShell.vue'
import { CANDIDATE_REASON_TEXT, daysSince, EXCLUSION_TEXT, isAlreadyNotified, isNewInRun, isPartial, isRunning, latestReport, needsReviewCount, needsReviewRow, revoke, runNow, type RevocationCandidate, type RevocationReport } from '../lib/revocation.ts'
import { DONE_TEXT } from '../lib/status.ts'
import { REASONS } from '../lib/requestView.ts'
import { usd } from '../lib/costImpact.ts'
import SaasMark from '../components/SaasMark.vue'

// S-04 오늘의 회수 점검 (IT 권한 관리 · 최종 승인자).
// 읽는 순서: 언제 점검했나 → 얼마나 줄일 수 있나(요약 숫자) → 누구의 어떤 권한인가(표) → 왜(사유 · 근거).
// 회수는 서버가 can_revoke를 준 후보만, 확인 창을 거쳐 실행한다. 다시 점검은 결과를 대신하지 않는 보조 동작이라 상태 줄 안의 작은 버튼으로 둔다.
const report = ref<RevocationReport | null>(null)
const mock = ref(false)
const loading = ref(true)
const running = ref(false)
const error = ref('')
type Tab = 'NEW' | 'NOTIFIED' | 'ALL'
const tab = ref<Tab>('NEW')

const all = computed(() => report.value?.candidates ?? [])
const run = computed(() => report.value?.run ?? null)
// 신규 = 이번 점검에서 처음 알린 후보, 이미 알린 = 앞선 점검에서 알렸고 아직 판단 대기. 유지 · 제외 후보는 '전체'에만.
const fresh = computed(() => all.value.filter(c => isNewInRun(c, run.value)))
const notified = computed(() => all.value.filter(c => isAlreadyNotified(c, run.value)))
const rows = computed(() => tab.value === 'NEW' ? fresh.value : tab.value === 'NOTIFIED' ? notified.value : all.value)
const failed = computed(() => run.value?.status === 'FAILED')
const busy = computed(() => running.value || isRunning(run.value))
// 규격 6: 점검 완료는 사유별 문구(회수 후보 점검 완료 / 신규 회수 후보 없음). 실패는 사유 코드 문구.
const runResult = computed(() => run.value?.status === 'DONE' && run.value.reason_code ? DONE_TEXT[run.value.reason_code]?.headline ?? null : null)
// 일부만 조회된 실패는 안내를 띄우되 찾은 후보는 보여 준다.
const partial = computed(() => isPartial(report.value))
const showResult = computed(() => !!report.value && (!failed.value || partial.value))
const extra = computed(() => needsReviewCount(report.value))
const failText = computed(() => (run.value?.reason_code && REASONS[run.value.reason_code]?.title) || '점검 중 오류가 발생했어요')
const monthly = computed(() => report.value?.summary.monthly_saving ?? 0)
const pending = computed(() => notified.value.reduce((n, c) => n + c.monthly_cost, 0))

const tabs = computed(() => [
  { key: 'NEW' as const, label: '새로 찾은 후보', count: fresh.value.length },
  { key: 'NOTIFIED' as const, label: '이미 알린 후보', count: notified.value.length },
  { key: 'ALL' as const, label: '전체', count: all.value.length },
])

function when(iso?: string | null) {
  if (!iso) return '–'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function initials(name: string) { return name.slice(-2) }
function idle(c: RevocationCandidate) {
  const d = daysSince(c.last_used_at)
  // 서버가 사용일을 안 준 것(정보 없음)과 한 번도 안 쓴 것(기록 없음)을 섞지 않는다.
  if (d === null && c.usage_known === false) return { text: '정보 없음', level: 0 }
  return d === null ? { text: '기록 없음', level: 3 } : { text: `${d}일 전`, level: d >= 60 ? 3 : d >= 30 ? 2 : 1 }
}

function fail(e: unknown) {
  error.value = e instanceof ApiError && e.status === 404
    ? '아직 실행한 점검이 없어요. [지금 다시 점검]을 눌러 주세요.'
    : e instanceof ApiError && e.status === 409 ? '이미 진행 중인 점검이 있어요. 잠시 뒤 결과를 다시 불러올게요.'
    : e instanceof ApiError && e.status === 403 ? '이 계정에 허용된 점검 범위가 아니에요.'
    : `점검 결과를 불러오지 못했어요. ${(e as Error)?.message ?? ''}`
}
async function load() {
  loading.value = true; error.value = ''
  try { ({ report: report.value, mock: mock.value } = await latestReport()) } catch (e) { fail(e) } finally { loading.value = false }
}
async function runScan() {
  if (running.value) return
  running.value = true; error.value = ''
  try { ({ report: report.value, mock: mock.value } = await runNow()); tab.value = 'NEW' } catch (e) { fail(e) } finally { running.value = false }
}
onMounted(load)

// 회수 실행: 사람이 확인 창에서 한 번 더 결정한다. 실패하면 창을 닫지 않고 이유를 보여 준다.
const confirming = ref<RevocationCandidate | null>(null)
const revoking = ref(false)
const revokeError = ref('')
const done = ref('')
// 버튼과 안내 문구는 같은 조건을 쓴다: 서버가 허용 · 아직 판단 대기 · 회수 대상 id가 있는 후보만.
function revocable(c: RevocationCandidate) { return !!c.can_revoke && c.candidate_status === 'PENDING_REVIEW' && !!c.target_id }
const canRevokeAny = computed(() => all.value.some(revocable))
// 확인 창: 열 때 창 안으로 초점을 옮기고, 열린 동안 Tab을 창 안에 가두고, 닫을 때 원래 버튼으로 돌려준다.
const modalBox = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null
async function askRevoke(c: RevocationCandidate) {
  opener = document.activeElement as HTMLElement | null
  confirming.value = c; revokeError.value = ''; done.value = ''
  await nextTick()
  modalBox.value?.querySelector<HTMLElement>('.rv-btn-ghost')?.focus()
}
function closeRevoke() {
  if (revoking.value) return // 요청 중에는 닫지 않는다(진행 중인 회수를 놓치지 않게)
  confirming.value = null
  opener?.focus(); opener = null
}
function trapTab(e: KeyboardEvent) {
  const items = Array.from(modalBox.value?.querySelectorAll<HTMLElement>('button:not([disabled])') ?? [])
  if (!items.length) return
  const first = items[0], last = items[items.length - 1]
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}
async function doRevoke() {
  const c = confirming.value
  if (!c || revoking.value) return
  revoking.value = true; revokeError.value = ''
  try {
    await revoke(c.target_id!)
    done.value = `${c.user_name || '대상자'}님의 ${c.platform} 권한을 회수했어요${c.cost_known !== false ? ` · 월 ${usd(c.monthly_cost)} 절감` : ''}`
    revoking.value = false; closeRevoke()
    await load()
    tab.value = 'ALL' // 회수된 후보는 '전체'에만 남으므로, 완료 배지가 보이는 탭으로 옮긴다
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      // 409는 이미 회수됨만이 아니다(사용 재개 · 유지 승인 · 점검 미완료 · 키 충돌). 이미 회수됨만 그렇게 말하고, 나머지는 서버 이유를 그대로 보인다.
      // 어느 경우든 최신 상태를 다시 불러오고, 창을 닫으므로 안내는 창 밖(하단 안내)에 남긴다.
      done.value = e.code === 'ALREADY_REVOKED' ? '이미 회수된 후보예요. 목록을 다시 불러왔어요.' : `회수하지 않았어요 · ${e.message}`
      revoking.value = false; closeRevoke(); await load(); tab.value = 'ALL'
    } else revokeError.value = e instanceof ApiError && e.status >= 500
      ? '회수 결과를 확인하지 못했어요. 목록을 다시 불러와 현재 상태를 확인해 주세요.'
      : `회수하지 못했어요. ${(e as Error)?.message ?? ''}`
  } finally { revoking.value = false }
}
// 10. 점검이 진행 중(접수 · 선별 · 결과 저장)인 보고서를 받으면 끝날 때까지 3초마다 다시 불러온다. 화면을 떠나면 멈춘다.
let follow: number | undefined
watch(report, () => {
  window.clearTimeout(follow)
  if (isRunning(run.value) && !running.value) follow = window.setTimeout(async () => {
    try { ({ report: report.value, mock: mock.value } = await latestReport()) } catch (e) { fail(e) }
  }, 3000)
}, { immediate: true })
onBeforeUnmount(() => window.clearTimeout(follow))

const help = {
  howto: [
    { t: '[지금 다시 점검]으로 점검해요', d: 'TF가 끝났거나 오래 쓰지 않은 유료 권한을 찾아요. 자동 점검(매일 09:00)은 담당 범위를 켜야 돌아가요(기본은 꺼짐)' },
    { t: '새로 찾은 후보만 먼저 보여 줘요', d: '이미 알린 후보는 다시 알리지 않아요. "이미 알린 후보" 탭에서 따로 볼 수 있어요' },
    { t: '회수는 사람이 결정해요', d: '후보와 근거, 줄일 수 있는 금액을 보고 [회수]를 누르면 확인 창에서 한 번 더 확인한 뒤 회수해요. 회수 버튼은 실행 권한이 있는 담당자에게, 아직 처리되지 않은 후보에만 보여요' },
  ],
  faqs: [
    { q: '어떤 기준으로 후보가 되나요?', a: 'TF가 끝난 뒤 30일 넘게 쓰지 않았고, 다른 TF 소속이나 유지 승인이 없는 유료 권한이에요 (시연용 가정 기준).' },
    { q: '계속 필요한 권한이면요?', a: '유지 승인이 있으면 다음 점검부터 후보에서 빠져요. 유지 승인 기록은 이번 범위에서는 담당자가 따로 남겨요.' },
  ],
}
</script>

<template>
  <AppShell :help="help">
    <div class="rv">
      <header class="rv-head">
        <p class="rv-crumb">회수 점검<span v-if="mock" class="rv-mock">목업 데이터</span></p>
        <h1>오늘의 회수 점검</h1>
        <p class="rv-sub">끝난 TF나 오래 쓰지 않은 유료 권한을 매일 찾아 알려 드려요</p>
      </header>

      <div class="rv-status" aria-live="polite">
        <span class="rv-dot" :class="{ run: busy, bad: failed }" aria-hidden="true" />
        <p class="rv-status-t">
          <template v-if="busy">지금 점검하고 있어요…</template>
          <template v-else-if="run">
            <b v-if="runResult">{{ runResult }}<template v-if="extra"> · 추가 확인 {{ extra }}건</template></b><span v-if="runResult" class="rv-sep" aria-hidden="true">·</span>
            마지막 점검 <b class="rv-num">{{ when(run.finished_at ?? run.started_at) }}</b>
            <span class="rv-sep" aria-hidden="true">·</span>{{ run.trigger === 'MANUAL' ? '직접 실행' : run.trigger === 'SCHEDULE' ? '매일 09:00 자동 실행' : '점검 실행' }}
          </template>
          <template v-else>[지금 다시 점검]으로 점검해요 · 자동 점검(매일 09:00)은 담당 범위를 켜면 돌아가요</template>
        </p>
        <button type="button" class="rv-run" :disabled="busy" @click="runScan">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" /></svg>
          {{ busy ? '점검하는 중' : '지금 다시 점검' }}
        </button>
      </div>

      <p v-if="error" class="rv-alert" role="alert">{{ error }}</p>
      <p v-else-if="partial" class="rv-alert" role="alert">점검이 중간에 멈춰 일부만 조회됐어요.{{ all.length ? ' 아래는 그때까지 찾은 후보예요.' : '' }} 다시 점검해 주세요.</p>
      <p v-else-if="failed" class="rv-alert" role="alert">{{ failText }}. 다시 점검해 주세요.</p>

      <!-- 요약 숫자: 처음 로딩 중에는 같은 자리에 회색 블록을 둬서 화면이 튀지 않게 한다. -->
      <section class="rv-kpis" aria-label="점검 요약">
        <template v-if="loading && !report"><div v-for="i in 4" :key="i" class="rv-kpi sk" /></template>
        <template v-else-if="showResult && report">
          <div class="rv-kpi">
            <div class="kh"><p class="k">새로 찾은 후보</p><span class="ki" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg></span></div>
            <p class="v"><span class="rv-num">{{ report.summary.new_count }}</span><small>건</small></p>
            <p class="d">오늘 처음 찾은 유료 권한</p>
          </div>
          <div class="rv-kpi" :class="{ hero: monthly > 0 }">
            <div class="kh"><p class="k">월 절감 예상</p><span class="ki" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M17 7H9.5a3 3 0 0 0 0 6h5a3 3 0 0 1 0 6H6" /></svg></span></div>
            <p class="v"><span class="rv-num">{{ usd(monthly) }}</span></p>
            <p class="d">{{ fresh.length + notified.length > 1 ? `아직 회수 안 된 후보 ${fresh.length + notified.length}건을 모두 회수하면` : '회수하면 매달 줄어드는 금액' }}</p>
          </div>
          <div class="rv-kpi">
            <div class="kh"><p class="k">연간 환산</p><span class="ki" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg></span></div>
            <p class="v"><span class="rv-num">{{ usd(monthly * 12) }}</span></p>
            <p class="d">월 절감 예상 × 12</p>
          </div>
          <div class="rv-kpi muted">
            <div class="kh"><p class="k">이미 알린 후보</p><span class="ki" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0" /></svg></span></div>
            <p class="v"><span class="rv-num">{{ notified.length }}</span><small>건 · 월 {{ usd(pending) }}</small></p>
            <p class="d">아직 회수되지 않은 권한</p>
          </div>
        </template>
      </section>

      <section v-if="showResult" class="rv-panel" aria-labelledby="rv-list-h">
        <div class="rv-panel-head">
          <h2 id="rv-list-h" class="rv-sr">회수 후보 목록</h2>
          <div class="rv-tabs" role="tablist" aria-label="후보 보기">
            <button v-for="t in tabs" :key="t.key" type="button" role="tab" class="rv-tab"
              :aria-selected="tab === t.key" @click="tab = t.key">
              {{ t.label }}<span class="rv-count">{{ t.count }}</span>
            </button>
          </div>
          <p class="rv-note">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>
            <template v-if="mock">실제 회수는 하지 않아요. 기존 절차로 진행해 주세요</template>
            <template v-else-if="canRevokeAny">[회수]를 누르면 확인 후 바로 권한을 회수해요</template>
            <template v-else>현재 회수 가능한 후보가 없어요</template>
          </p>
        </div>

        <div v-if="!rows.length" class="rv-empty">
          <div class="rv-empty-ic" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
          </div>
          <!-- 추가 확인 건이 있으면 '후보 없음'이 아니다: 같은 빈 화면 문구를 쓰지 않는다. -->
          <p class="t">{{ tab !== 'NEW' ? '표시할 후보가 없어요' : extra ? '새로 알릴 후보는 없어요' : '신규 회수 후보 없음' }}</p>
          <p class="d">{{ tab !== 'NEW' ? '다른 탭을 확인해 주세요.' : extra ? `아래 추가 확인 ${extra}건을 확인해 주세요.` : '이미 알린 후보는 다시 알리지 않아요.' }}</p>
        </div>

        <table v-else class="rv-table">
          <thead>
            <tr><th>대상자</th><th>SaaS · 권한</th><th>마지막 사용</th><th class="num">월 비용</th><th>사유와 근거</th><th>상태</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in rows" :key="c.id">
              <td>
                <div class="rv-who">
                  <span v-if="c.user_name" class="rv-av" aria-hidden="true">{{ initials(c.user_name) }}</span>
                  <div><b v-if="c.user_name">{{ c.user_name }}</b><span v-else class="rv-meta rv-noname">이름 미제공</span><span class="rv-meta">{{ c.tf_id ?? (c.user_id ? '소속 TF 없음' : '') }}</span></div>
                </div>
              </td>
              <td>
                <div class="rv-saas">
                  <SaasMark :name="c.platform" :size="34" tile />
                  <div><b>{{ c.platform }}</b><span class="rv-meta">{{ c.resource }}</span></div>
                </div>
              </td>
              <td><span class="rv-idle" :class="`l${idle(c).level}`">{{ idle(c).text }}</span></td>
              <td class="num"><template v-if="c.cost_known !== false"><b class="rv-num">{{ usd(c.monthly_cost) }}</b><span class="rv-meta">/ 월</span></template><span v-else class="rv-meta">비용 미확인</span></td>
              <td class="rv-why">
                <p>{{ c.reason }}</p>
                <div class="rv-refs">
                  <span v-if="CANDIDATE_REASON_TEXT[c.candidate_reason_code]" class="rv-ref">{{ CANDIDATE_REASON_TEXT[c.candidate_reason_code] }}</span>
                  <span v-if="c.policy_ref" class="rv-ref law">{{ c.policy_ref }}</span>
                </div>
              </td>
              <td>
                <span v-if="c.candidate_status === 'RECLAIMED'" class="rv-badge done">회수 완료<template v-if="c.reclaimed_at"> · {{ when(c.reclaimed_at) }}</template></span>
                <span v-else-if="c.candidate_status === 'RETAINED'" class="rv-badge kept">유지 승인</span>
                <span v-else-if="c.candidate_status === 'EXCLUDED'" class="rv-badge kept">제외 · {{ EXCLUSION_TEXT[c.exclusion_reason_code ?? ''] ?? '조건 미충족' }}</span>
                <span v-else-if="isNewInRun(c, run)" class="rv-badge new">신규</span>
                <span v-else-if="c.notified_at" class="rv-badge sent">알림 {{ when(c.notified_at) }}</span>
                <span v-else class="rv-badge kept">알림 전</span>
                <button v-if="revocable(c)" type="button" class="rv-revoke" @click="askRevoke(c)">회수</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 정보가 부족해 후보 판정을 못 한 건. 알림에는 넣지 않고 무엇이 필요한지만 남긴다. -->
      <section v-if="showResult && extra" class="rv-panel rv-extra" aria-labelledby="rv-extra-h">
        <div class="rv-extra-head">
          <h2 id="rv-extra-h">추가 확인 <span class="rv-num">{{ extra }}</span>건</h2>
          <p>정보가 부족해 후보인지 판단하지 못했어요. 알림은 보내지 않았어요</p>
        </div>
        <ul v-if="report?.needs_review?.length" class="rv-extra-list">
          <li v-for="(n, i) in report.needs_review.map(needsReviewRow)" :key="i">
            <b>{{ n.who }}</b><span class="rv-meta">{{ n.what }}</span>
            <span class="rv-need">필요한 정보: {{ n.missing.join(', ') }}</span>
          </li>
        </ul>
      </section>
    </div>
    <p v-if="done" class="rv-done" role="status">{{ done }}</p>
    <div v-if="confirming" class="rv-modal" role="dialog" aria-modal="true" aria-labelledby="rv-modal-t" @keydown.esc="closeRevoke" @keydown.tab="trapTab">
      <button type="button" class="rv-scrim" aria-label="닫기" tabindex="-1" :disabled="revoking" @click="closeRevoke" />
      <div ref="modalBox" class="rv-modal-box">
        <h2 id="rv-modal-t">이 권한을 회수할까요?</h2>
        <dl class="rv-modal-dl">
          <dt>대상자</dt><dd>{{ confirming.user_name || '이름 미제공' }}</dd>
          <dt>SaaS</dt><dd>{{ confirming.platform }}<template v-if="confirming.resource"> · {{ confirming.resource }}</template></dd>
          <dt>줄어드는 비용</dt><dd><template v-if="confirming.cost_known !== false">월 {{ usd(confirming.monthly_cost) }}</template><template v-else>비용 미확인</template></dd>
          <dt>근거</dt><dd>{{ confirming.policy_ref || '—' }}</dd>
        </dl>
        <p class="rv-modal-note">회수하면 이 사용자는 바로 쓸 수 없어요. 다시 필요하면 새로 요청해야 해요.</p>
        <p v-if="revokeError" class="rv-modal-err" role="alert">{{ revokeError }}</p>
        <div class="rv-modal-act">
          <button type="button" class="rv-btn-ghost" :disabled="revoking" @click="closeRevoke">취소</button>
          <button type="button" class="rv-btn-danger" :disabled="revoking" @click="doRevoke">{{ revoking ? '회수 중…' : '회수하기' }}</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.rv { padding: 48px 0 40px; display: flex; flex-direction: column; gap: 16px; }
.rv-head h1 { margin: 6px 0 0; font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }
.rv-crumb { margin: 0; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--uo-primary-ink); }
.rv-mock { font-size: 11px; font-weight: 700; color: var(--uo-review); background: var(--uo-review-bg); border-radius: 999px; padding: 2px 9px; }
.rv-sub { margin: 6px 0 0; font-size: 15px; color: var(--uo-muted); }
.rv-num { font-family: var(--uo-font-en); font-variant-numeric: tabular-nums; }
.rv-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

.rv-status { display: flex; align-items: center; gap: 12px; background: #fff; border: 1px solid var(--uo-line); border-radius: 14px; padding: 8px 8px 8px 16px; box-shadow: 0 1px 2px rgba(20,26,51,.04); }
.rv-dot { width: 8px; height: 8px; border-radius: 50%; background: #22C55E; box-shadow: 0 0 0 4px #DCFCE7; flex: 0 0 8px; }
.rv-dot.run { background: var(--uo-primary); box-shadow: 0 0 0 4px var(--uo-primary-soft); animation: rv-pulse 1s ease-in-out infinite; }
.rv-dot.bad { background: var(--uo-bad); box-shadow: 0 0 0 4px var(--uo-bad-bg); }
.rv-status-t { margin: 0; flex: 1; font-size: 14px; color: var(--uo-ink-2); }
.rv-status-t b { color: var(--uo-ink); font-weight: 600; }
.rv-sep { margin: 0 6px; color: var(--uo-line-strong); }
.rv-run { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: 10px; border: 1px solid #D5D9EA; background: #fff; color: var(--uo-ink-2); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; transition: background-color .15s, border-color .15s, color .15s; }
.rv-run:hover:not(:disabled) { background: var(--uo-primary-soft); border-color: #B9C0E8; color: var(--uo-primary-ink); }
.rv-run:focus-visible, .rv-tab:focus-visible { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
.rv-run:disabled { color: var(--uo-muted); cursor: progress; }
.rv-run:disabled svg { animation: rv-spin 1s linear infinite; }
.rv-alert { margin: 0; font-size: 14px; font-weight: 500; color: var(--uo-bad); background: var(--uo-bad-bg); border-radius: 10px; padding: 10px 14px; }

.rv-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.rv-kpi { background: #fff; border: 1px solid var(--uo-line); border-radius: 16px; padding: 18px 20px; display: flex; flex-direction: column; gap: 6px; min-height: 128px; box-shadow: 0 1px 2px rgba(20,26,51,.04); }
.rv-kpi .kh { display: flex; justify-content: space-between; align-items: center; }
.rv-kpi .ki { width: 30px; height: 30px; border-radius: 9px; display: inline-flex; align-items: center; justify-content: center; background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rv-kpi.hero .ki { background: rgba(255,255,255,.18); color: #fff; }
.rv-kpi.muted .ki { background: #EEF0F6; color: var(--uo-muted); }
.rv-kpi .k { margin: 0; font-size: 13px; font-weight: 600; color: var(--uo-muted); }
.rv-kpi .v { margin: 0; display: flex; align-items: baseline; gap: 6px; }
.rv-kpi .v .rv-num { font-size: 34px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; color: var(--uo-ink); }
.rv-kpi .v small { font-size: 14px; font-weight: 600; color: var(--uo-ink-2); }
.rv-kpi .d { margin: auto 0 0; font-size: 12px; color: var(--uo-muted); }
.rv-kpi.hero { background: linear-gradient(135deg, #3B4BD8 0%, #5B5BF0 55%, #7A5CF0 100%); border-color: transparent; box-shadow: 0 10px 24px rgba(59,75,216,.22); }
.rv-kpi.hero .k, .rv-kpi.hero .d { color: rgba(255,255,255,.82); }
.rv-kpi.hero .v .rv-num { color: #fff; }
.rv-kpi.muted { background: #FAFBFE; }
.rv-kpi.sk { background: linear-gradient(90deg, #F0F2F8 25%, #F7F8FC 50%, #F0F2F8 75%); background-size: 200% 100%; animation: rv-sk 1.2s linear infinite; }

.rv-panel { background: #fff; border: 1px solid var(--uo-line); border-radius: 16px; overflow: hidden; box-shadow: 0 1px 2px rgba(20,26,51,.04); }
.rv-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--uo-line); flex-wrap: wrap; }
.rv-tabs { display: flex; gap: 4px; background: var(--uo-bg); border-radius: 10px; padding: 3px; }
.rv-tab { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: var(--uo-muted); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.rv-tab[aria-selected="true"] { background: #fff; color: var(--uo-ink); box-shadow: 0 1px 3px rgba(20,26,51,.12); }
.rv-count { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; background: #E4E7F2; color: var(--uo-ink-2); font-family: var(--uo-font-en); font-size: 12px; display: inline-flex; align-items: center; justify-content: center; }
.rv-tab[aria-selected="true"] .rv-count { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rv-note { margin: 0; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--uo-muted); }

.rv-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.rv-table th { text-align: left; font-size: 12px; font-weight: 600; color: var(--uo-muted); background: #FAFBFE; padding: 10px 16px; border-bottom: 1px solid var(--uo-line); white-space: nowrap; }
.rv-table td { padding: 16px; border-bottom: 1px solid var(--uo-line); vertical-align: middle; }
.rv-table tbody tr:last-child td { border-bottom: 0; }
.rv-table tbody tr:hover { background: #FAFBFE; }
.rv-table .num { text-align: right; white-space: nowrap; }
.rv-who, .rv-saas { display: flex; align-items: center; gap: 10px; }
.rv-who b, .rv-saas b { font-weight: 600; }
.rv-meta { display: block; margin-top: 2px; font-size: 12px; color: var(--uo-muted); font-weight: 400; }
.num .rv-meta { display: inline; margin-left: 3px; }
.rv-av { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; background: var(--uo-primary-soft); color: var(--uo-primary-ink); font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.rv-logo { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 9px; font-family: var(--uo-font-en); font-size: 13px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.rv-idle { display: inline-flex; align-items: center; gap: 6px; font-family: var(--uo-font-en); font-size: 13px; white-space: nowrap; }
.rv-idle::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.rv-idle.l0 { color: var(--uo-muted); } .rv-noname { margin: 0; font-size: 14px; }
.rv-idle.l1 { color: var(--uo-ink-2); } .rv-idle.l2 { color: var(--uo-review); } .rv-idle.l3 { color: var(--uo-bad); }
.rv-why { max-width: 420px; }
.rv-why p { margin: 0; line-height: 1.5; color: var(--uo-ink-2); }
.rv-refs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.rv-ref { display: inline-block; font-size: 11px; font-weight: 600; color: var(--uo-primary-ink); background: var(--uo-primary-soft); border-radius: 6px; padding: 3px 8px; }
.rv-ref.law { color: var(--uo-ink-2); background: #fff; border: 1px solid var(--uo-line); }
.rv-badge { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.rv-badge.new { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rv-badge.sent { background: #F0F2F8; color: var(--uo-muted); }
.rv-badge.done { background: #FDECEC; color: #B42318; }
.rv-revoke { display: block; margin-top: 8px; height: 30px; padding: 0 14px; border: 1px solid #E4A4A4; border-radius: 999px; background: #fff; color: #B42318; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
.rv-revoke:hover, .rv-revoke:focus-visible { background: #FDECEC; }
.rv-done { position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%); margin: 0; padding: 12px 20px; border-radius: 12px; background: var(--uo-ink); color: #fff; font-size: 14px; font-weight: 600; z-index: 40; }
.rv-modal { position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; padding: 16px; }
.rv-scrim { position: absolute; inset: 0; border: 0; padding: 0; background: rgba(20,26,51,0.4); cursor: pointer; }
.rv-modal-box { position: relative; width: 440px; max-width: 100%; background: #fff; border-radius: 20px; padding: 28px; box-shadow: 0 20px 60px rgba(20,26,51,0.25); }
.rv-modal-box h2 { margin: 0 0 16px; font-size: 20px; font-weight: 700; }
.rv-modal-dl { display: grid; grid-template-columns: 96px 1fr; gap: 8px 12px; margin: 0 0 16px; font-size: 14px; }
.rv-modal-dl dt { color: var(--uo-muted); } .rv-modal-dl dd { margin: 0; font-weight: 600; }
.rv-modal-note { margin: 0 0 12px; font-size: 14px; line-height: 1.6; color: var(--uo-ink-2); background: #FFF6E5; border-radius: 10px; padding: 10px 12px; }
.rv-modal-err { margin: 0 0 12px; font-size: 14px; color: var(--uo-bad); font-weight: 600; }
.rv-modal-act { display: flex; justify-content: flex-end; gap: 8px; }
.rv-btn-ghost, .rv-btn-danger { height: 40px; padding: 0 18px; border-radius: 12px; font: inherit; font-size: 14px; font-weight: 700; cursor: pointer; }
.rv-btn-ghost { border: 1px solid var(--uo-line); background: #fff; color: var(--uo-ink-2); }
.rv-btn-danger { border: 0; background: #B42318; color: #fff; }
.rv-btn-ghost:disabled, .rv-btn-danger:disabled { opacity: .6; cursor: default; }
.rv-badge.kept { background: var(--uo-ok-bg); color: var(--uo-ok); }

.rv-empty { padding: 48px 16px; text-align: center; }
.rv-empty-ic { width: 56px; height: 56px; margin: 0 auto 14px; border-radius: 50%; background: var(--uo-primary-soft); color: var(--uo-primary); display: flex; align-items: center; justify-content: center; }
.rv-empty .t { margin: 0; font-size: 16px; font-weight: 600; }
.rv-empty .d { margin: 6px 0 0; font-size: 14px; color: var(--uo-muted); }

@keyframes rv-pulse { 50% { opacity: .35; } }
@keyframes rv-spin { to { transform: rotate(360deg); } }
@keyframes rv-sk { to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .rv-dot.run, .rv-run:disabled svg, .rv-kpi.sk { animation: none; } }
@media (max-width: 1000px) { .rv-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) {
  .rv { padding-top: 24px; }
  .rv-status { flex-wrap: wrap; }
  .rv-table thead { display: none; }
  .rv-table, .rv-table tbody, .rv-table tr, .rv-table td { display: block; width: 100%; }
  .rv-table tr { padding: 12px 16px; border-bottom: 1px solid var(--uo-line); }
  .rv-table td { border: 0; padding: 4px 0; }
  .rv-table .num { text-align: left; }
}
.rv-extra-head { padding: 16px 20px; border-bottom: 1px solid var(--uo-line); }
.rv-extra-head h2 { margin: 0; font-size: 16px; font-weight: 700; }
.rv-extra-head p { margin: 4px 0 0; font-size: 13px; color: var(--uo-muted); }
.rv-extra-list { list-style: none; margin: 0; padding: 0; }
.rv-extra-list li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; padding: 12px 20px; border-bottom: 1px solid var(--uo-line); font-size: 14px; }
.rv-extra-list li:last-child { border-bottom: 0; }
.rv-need { flex-basis: 100%; color: var(--uo-ink-2); }
@media (min-width: 720px) { .rv-need { flex-basis: auto; margin-left: auto; } }
</style>
