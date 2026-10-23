<script setup lang="ts">
import SaasMark from '../components/SaasMark.vue'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError, type Problem } from '../api'
import { decide as sendDecision, getProblem, isV2, myTurn, resume } from '../lib/data'
import AppShell from '../components/AppShell.vue'
import StageBar from '../components/StageBar.vue'
import { platformOf, roleText } from '../lib/platforms'
import CostImpactCard from '../components/CostImpactCard.vue'
import { costImpactOf, usd } from '../lib/costImpact.ts'
import { checksOf, evidenceDocsOf, GROUP_LABEL } from '../lib/evidenceView.ts'
import { decisionSummaryOf } from '../lib/decisionSummary.ts'
import { usePolling } from '../lib/polling'
import { aiMessageOf, approverEventsOf, isMidStep, judgmentOf, approverNoticeOf, approverSummaryOf, evidenceOf, noticeOf, proposalOf, requesterEventsOf, REJECT_CHIPS, stagesOf, summaryOf } from '../lib/requestView'
import { isAlreadyHas, isGuidanceComplete, isTerminal, needsRefresh, statusOf } from '../lib/status'
import { shortWhen } from '../lib/time'
import { currentUser } from '../session'

const route = useRoute()
const id = String(route.params.id)
// 요청 번호는 UUID다. 다른 값(예: ..%2Fauth%2Fme)이 API 경로로 들어가지 않게 먼저 거른다.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const item = ref<Problem | null>(null)
const error = ref('')
const isRequester = computed(() => currentUser.value?.role !== 'APPROVER')
const back = computed(() => isRequester.value ? '/' : '/approvals')

async function load() {
  if (!UUID.test(id)) { error.value = '요청을 찾을 수 없어요.'; return false }
  try {
    item.value = await getProblem(id)
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
  return needsRefresh(item.value)
}
const polling = usePolling(load)


const p = computed(() => item.value)
const guidanceComplete = computed(() => !!p.value && isGuidanceComplete(p.value))
const platform = computed(() => p.value ? platformOf(p.value.platform) : null)
// 제목은 쉬운 말(플랫폼 + 권한 설명), 정확한 코드(대상 자원 · 권한)는 아래 작은 글씨로. 승인자는 무엇을 승인하는지 코드로 확인해야 한다.
const roleKo = computed(() => p.value ? roleText(p.value.platform, p.value.requested_role) : null)
const titleText = computed(() => !p.value || !platform.value ? ''
  : roleKo.value ? `${platform.value.label} ${roleKo.value} 권한`
  : p.value.requested_role ? `${platform.value.label} · ${p.value.requested_role}` : platform.value.label)
const stages = computed(() => p.value ? stagesOf(p.value) : [])
const summary = computed(() => !p.value ? '' : isRequester.value ? summaryOf(p.value) : approverSummaryOf(p.value))
// 안내 성공은 요청자도 진단을 본다. 실제 검토 필요 · 거절의 판단 근거는 승인자에게만 표시한다.
// 판단 문장은 reason_code로 만든다(서버 문장은 모르는 사유 코드일 때만). 요청자 · 승인자 문장이 다르다.
// 승인 대기인데 지금 내 차례가 아니면(이미 내 단계를 승인했거나 아직 앞 단계) '승인하면 …'이 아니라 진행 상황을 말한다.
const aiMessage = computed(() => !p.value ? null : isRequester.value ? aiMessageOf(p.value)
  : p.value.status === 'WAITING_APPROVAL' && p.value.reason_code === 'ELIGIBLE' && isV2() && !myTurn(p.value)
    ? '규정과 예산 조건을 모두 충족해요. 다른 단계 승인을 기다리고 있어요.'
    : judgmentOf(p.value, true))
// 승인자는 plan의 자원 이름(resource_key)까지 받는다. 요청자 응답에는 plan이 없다.
const resourceName = computed(() => (!isRequester.value && p.value?.plan?.resource_key) || '')
const proposal = computed(() => {
  const base = p.value && platform.value ? proposalOf(p.value, resourceName.value || platform.value.label) : null
  // 권한 설명이 있으면 같은 문장을 쉬운 말로: "Snowflake 웨어하우스 이용 권한(USAGE)을 부여하는 판단안이에요."
  if (!base || guidanceComplete.value || !roleKo.value || !platform.value || !p.value) return base
  return `${platform.value.label} ${roleKo.value} 권한(${p.value.requested_role})을 부여하는 판단안이에요.`
})
// S-02 비용 영향 카드는 승인자에게만 보인다(예산 판단은 승인자의 일). 요청자에게는 안내 카드의 이유만 보인다.
// 서버 cost_impact가 오면 그 값, 아직 없으면 목업 모드(VITE_UO_MOCK)에서만 보인다.
const cost = computed(() => !isRequester.value && p.value ? costImpactOf(p.value) : null)
const docs = computed(() => !isRequester.value && p.value ? evidenceDocsOf(p.value, platform.value?.label ?? null) : [])
// 원문보다 결론을 먼저: 규칙이 확인한 조건을 한 줄씩. 원문은 접어 두고 필요할 때 펼친다.
const checks = computed(() => p.value ? checksOf(p.value, docs.value) : [])
const rules = computed(() => checks.value.filter(c => !c.info))
const failed = computed(() => rules.value.filter(c => !c.ok).length)
const who = computed(() => evidence.value.facts.find(f => f.k === '요청자 소속')?.v ?? '')
// 승인 상자의 근거 칩을 누르면 판단 근거의 해당 문서로 내려가 펼치고 잠깐 강조한다. 칩 없이 '외 n'은 근거 맨 위로.
const openDocs = ref(new Set<string>())
const flashDoc = ref('')
function onToggle(id: string, e: Event) {
  const next = new Set(openDocs.value)
  if ((e.target as HTMLDetailsElement).open) next.add(id); else next.delete(id)
  openDocs.value = next
}
function jumpTo(id?: string) {
  if (id) { openDocs.value = new Set([...openDocs.value, id]) }
  requestAnimationFrame(() => {
    const el = document.getElementById(id ? `ev-${id}` : 'ev-top')
    if (!el) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    if (id) { flashDoc.value = id; window.setTimeout(() => { if (flashDoc.value === id) flashDoc.value = '' }, 1600) }
    ;(el.querySelector('summary') as HTMLElement | null)?.focus({ preventScroll: true })
  })
}
// 상한표는 처음엔 이 요청의 플랫폼 행만 보여 주고, 필요하면 전체를 펼친다.
const openTables = ref(new Set<string>())
function toggleTable(key: string) {
  const next = new Set(openTables.value)
  if (next.has(key)) next.delete(key); else next.add(key)
  openTables.value = next
}
const evidence = computed(() => !isRequester.value && p.value ? evidenceOf(p.value) : { facts: [], docs: [] })
const notice = computed(() => p.value && isRequester.value ? noticeOf(p.value) : null)
const aprNotice = computed(() => p.value && !isRequester.value ? approverNoticeOf(p.value) : null)
const events = computed(() => {
  if (!p.value) return []
  if (!isRequester.value) return approverEventsOf(p.value)
  return requesterEventsOf(p.value)
})
const perm = computed(() => {
  const x = p.value
  if (!x?.requested_role || isGuidanceComplete(x)) return null
  const map: Partial<Record<Problem['status'], { label: string; tone: string }>> = {
    EXECUTING: { label: '부여 중', tone: 'run' },
    DONE: { label: '✓ 부여 · 확인됨', tone: 'ok' },
    FAILED: { label: '✕ 실패', tone: 'bad' },
  }
  const s = map[x.status]
  if (!s || (x.status === 'DONE' && !x.decided_at)) return null
  return { role: x.requested_role, ...s, title: '부여 결과' }
})
// 요청 번호는 DB가 만든 36자 UUID라 앞 8자리만 보여 주고, 전체는 복사로만 쓴다(서버 로그 조회용).
const shortId = computed(() => p.value ? '#' + p.value.id.slice(0, 8).toUpperCase() : '')
const copied = ref(false)
async function copyId() {
  if (!p.value) return
  try { await navigator.clipboard.writeText(p.value.id); copied.value = true; window.setTimeout(() => { copied.value = false }, 1500) } catch { /* 복사 권한이 없으면 조용히 넘어간다 */ }
}
// 판단안 카드 안의 비용 한 줄. 자세한 비용 카드는 판단 근거 아래에 둔다.
const costLine = computed(() => {
  const c = cost.value?.impact
  if (!c) return null
  if (c.kind === 'NO_COST') return { big: '추가 비용 없음', sub: '' }
  return { big: `월 −${usd(c.monthly_cost)}`, sub: c.budget_before !== null && c.budget_after !== null ? `부서 잔여 ${usd(c.budget_before)} → ${usd(c.budget_after)}` : '' }
})
// 승인자 화면 맨 위 한 장 요약(결론 → 숫자 → 왜 괜찮은지 → 승인 순서). 승인 대기 · 보류일 때만.
const decision = computed(() => !isRequester.value && p.value ? decisionSummaryOf(p.value, titleText.value, cost.value?.impact ?? null, currentUser.value?.id) : null)
// 한 장 요약이 있고 조건을 모두 맞췄으면 조건 목록은 접어 둔다(요약은 역할·비용·승인 순서만 담으므로 나머지 근거는 펼쳐서 확인).
// 못 맞춘 조건이 있으면 처음부터 펼쳐 보인다.
const showChecks = computed(() => !decision.value || checks.value.some(c => !c.ok && !c.info))
function jumpCost() {
  const el = document.getElementById('cost-card')
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}
const record = computed(() => {
  const x = p.value
  if (!x) return []
  return [
    { k: '요청 시각', v: shortWhen(x.created_at) },
    { k: '마지막 변경', v: shortWhen(x.updated_at) },
    { k: '결정 시각', v: isGuidanceComplete(x) ? '해당 없음' : x.decided_at ? shortWhen(x.decided_at) : '아직 없음' },
    { k: '반영 확인', v: isGuidanceComplete(x) ? '해당 없음' : x.verification_ok === true ? '✓ 확인됨' : x.verification_ok === false ? '✕ 반영 안 됨' : '아직 없음' },
  ]
})

/* ---------- 승인 카드 (승인자 · 승인 대기일 때만) ---------- */
// v2는 현재 단계의 지정 승인자에게만 승인 상자를 보여 준다(서버도 막는다).
const canDecide = computed(() => !isRequester.value && !!p.value && myTurn(p.value))
// 보류 · 담당자 검토는 최신 조건으로 다시 분석할 수 있다(v2).
const canResume = computed(() => isV2() && !isRequester.value && !!p.value && (p.value.status === 'ON_HOLD' || p.value.status === 'MANUAL_REVIEW'))
const resuming = ref(false)
async function askResume() {
  if (!p.value || resuming.value) return
  resuming.value = true
  decideError.value = ''
  try { await resume(p.value) } catch (e) { decideError.value = (e as Error).message } finally { resuming.value = false; polling.restart() }
}
const memoOpen = ref(false)
const memo = ref('')
const rejecting = ref(false)
const rejPick = ref('')
const rejText = ref('')
const rejErr = ref(false)
const deciding = ref(false)
const decideError = ref('')
const rejReason = computed(() => [rejPick.value, rejText.value.trim()].filter(Boolean).join(' · '))

function pickChip(t: string) { rejPick.value = rejPick.value === t ? '' : t; rejErr.value = false }
function cancelReject() { rejecting.value = false; rejErr.value = false }

const toast = ref('')
let toastTimer: number | undefined
function flash(msg: string) { toast.value = msg; window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => { toast.value = '' }, 4500) }
async function decide(approved: boolean, hold = false) {
  const x = p.value
  if (!x || deciding.value) return
  if (!approved && !rejReason.value) { rejErr.value = true; return }
  deciding.value = true
  decideError.value = ''
  try {
    // 승인 카드에 보이는 계획(plan_hash)에 대해서만 결정한다. 그사이 계획이 바뀌면 서버가 409로 막는다.
    await sendDecision(x, approved ? 'APPROVE' : hold ? 'HOLD' : 'REJECT', approved ? memo.value.trim() : rejReason.value)
    rejecting.value = false
    const lastStep = (x.total_steps ?? 1) <= (x.current_step ?? 1)
    flash(approved ? (lastStep ? '승인했어요 · 권한을 부여하고 다시 조회해 확인할게요' : `${x.current_step ?? 1}단계 승인했어요 · 다음 승인자에게 넘어갔어요`)
      : hold ? '보류했어요 · 요청자에게 사유를 보냈어요' : '거절했어요 · 요청자에게 사유를 보냈어요')
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    decideError.value = status === 409 ? '그사이 이미 처리됐거나 승인 내용이 바뀌었어요. 최신 내용을 다시 불러왔어요. 확인하고 다시 결정해 주세요.'
      : status === 403 ? '이 요청의 지정 승인자만 결정할 수 있어요.'
      : status === 400 ? (e as Error).message
      : '결정을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  } finally {
    deciding.value = false
    polling.restart()
  }
}

const help = computed(() => isRequester.value ? requesterHelp : approverHelp)
const approverHelp = {
  howto: [
    { t: '판단안과 근거를 확인하세요', d: 'AI가 조회한 요청자 정보, 사내 규정 원문, 비용 영향이 왼쪽에 있어요' },
    { t: '승인하거나 거절하세요', d: '승인하면 바로 부여되고 다시 조회해 반영을 확인해요. 거절할 땐 사유가 필요해요' },
  ],
  faqs: [
    { q: '승인 메모 · 거절 사유는 누가 보나요?', a: '요청자에게 그대로 보여요. 판단 근거(규정 · 조회 결과)는 승인자에게만 보여요.' },
    { q: '결정하려는데 내용이 바뀌었다고 나와요', a: '그사이 AI가 계획을 다시 만들었거나 다른 곳에서 처리된 경우예요. 새로 불러온 내용을 확인하고 다시 결정해 주세요.' },
  ],
}
const requesterHelp = {
  howto: [
    { t: '진행 단계를 보세요', d: '권한 변경은 접수 → 판단안 → 승인 → 권한 부여 → 반영 확인 순서로 진행돼요. 안내 요청은 판단 후 안내 제공으로 완료돼요' },
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
        <h1 v-if="p && platform">{{ titleText }}</h1>
        <!-- 사람이 먼저 읽는 줄(누가 · 언제) → 승인 대상을 코드로 확인하는 회색 줄(대상 자원 · 권한 코드 · 요청 번호). -->
        <p v-if="p" class="rd-meta">
          <template v-if="isRequester">내가</template><template v-else><b>{{ p.requester_name }}</b><template v-if="p.employee_no"> ({{ p.employee_no }})</template> 님이</template>
          {{ shortWhen(p.created_at) }}에 요청했어요
        </p>
        <p v-if="p" class="rd-codes rd-en">
          <template v-if="resourceName">{{ resourceName }} · </template><template v-if="p.requested_role">{{ p.requested_role }} · </template>{{ shortId }}
        </p>
      </div>
      <span v-if="p" class="rd-badge" :class="statusOf(p).tone"><svg v-if="statusOf(p).tone === 'review'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin-right: 4px; vertical-align: -2px"><path d="M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6.5 19a5.5 5.5 0 0 1 11 0" /></svg>{{ statusOf(p).label }}</span>
    </div>

    <p v-if="error && !p" class="rd-state" role="alert">{{ error }} <RouterLink :to="back">돌아가기</RouterLink></p>
    <p v-else-if="!p" class="rd-state">불러오는 중…</p>

    <template v-if="p && platform">
      <p v-if="error" class="rd-warn" role="status">{{ error }}</p>
      <StageBar :stages="stages" :summary="summary" />

      <div class="rd-cols">
        <div class="rd-main">
          <section v-if="decision" class="rd-card rd-sum" :class="decision.tone" aria-labelledby="rd-sum-h">
            <span class="rd-sum-badge">{{ decision.badge }}</span>
            <h2 id="rd-sum-h" class="rd-sum-h">{{ decision.headline }}</h2>
            <p class="rd-sum-sub">{{ decision.sub }}</p>
            <div v-if="decision.numbers.length" class="rd-sum-nums">
              <div v-for="n in decision.numbers" :key="n.label" class="rd-sum-num"><b class="rd-en">{{ n.big }}</b><span>{{ n.label }}</span></div>
            </div>
            <template v-if="decision.checks.length">
              <p class="rd-sum-k">{{ decision.tone === 'ok' ? '왜 괜찮은가요' : '확인한 것' }}</p>
              <ul class="rd-sum-checks">
                <li v-for="c in decision.checks" :key="c.text">
                  <span class="rd-ck-ic" aria-hidden="true">✓</span>
                  <span>{{ c.text }}<span v-if="c.detail" class="rd-ck-d rd-en">{{ c.detail }}</span></span>
                  <button v-if="c.ref" type="button" class="rd-ck-ref" @click="jumpTo(c.ref.id)">{{ c.ref.label }}</button>
                </li>
              </ul>
            </template>
            <ol v-if="decision.steps.length" class="rd-sum-steps" aria-label="승인 순서">
              <li v-for="(st, i) in decision.steps" :key="i" :class="st.state"><b>{{ st.who }}</b><span>{{ st.label }}</span></li>
            </ol>
            <button v-if="docs.length" type="button" class="rd-link rd-sum-more" @click="jumpTo()">규정 원문 보기 ↓</button>
          </section>
          <!-- 결정이 끝난 뒤의 결과가 가장 중요한 정보라 맨 위. 승인 대기 중에는 제목 · 승인 상자와 같은 내용이라 두지 않는다. -->
          <section v-if="perm" class="rd-card" aria-labelledby="rd-pm">
            <h2 id="rd-pm">{{ perm.title }}</h2>
            <article class="rd-perm" :style="{ '--tc': platform.color }">
              <div class="rd-perm-head">
                <span class="rd-ptag" :style="{ background: platform.soft, color: platform.color }">
                  <SaasMark :platform="p.platform" :size="16" />{{ platform.label }}
                </span>
                <span class="rd-pstate" :class="perm.tone">{{ perm.label }}</span>
              </div>
              <h3 v-if="resourceName" class="rd-perm-target rd-en">{{ resourceName }}</h3>
              <p class="rd-perm-role">요청 권한 <strong>{{ roleKo ?? perm.role }}</strong><span v-if="roleKo" class="rd-code-sm rd-en">{{ perm.role }}</span></p>
              <p v-if="p.status === 'FAILED'" class="rd-perm-fail">총 3회 시도했지만 실패 · 운영 담당자가 확인 중</p>
            </article>
          </section>
          <section class="rd-card" aria-labelledby="rd-dg">
            <!-- 플랫폼 · 자원 · 권한은 대화가 아니라 요청 정보라서, 말풍선과 떨어진 제목 줄 오른쪽에 배지로 둔다. -->
            <div class="rd-card-head">
              <h2 id="rd-dg">{{ guidanceComplete && !isRequester ? '요청 내용과 안내' : aiMessage || proposal ? '요청 내용과 판단안' : '요청 내용' }}</h2>
              <div class="rd-facts" aria-label="요청 정보">
                <span class="rd-ptag" :style="{ background: platform.soft, color: platform.color }">
                  <SaasMark :platform="p.platform" :size="15" />{{ platform.label }}
                </span>
                <span v-if="resourceName" class="rd-fact rd-en">{{ resourceName }}</span>
                <span v-if="p.requested_role" class="rd-fact">{{ p.requested_role }}</span>
              </div>
            </div>
            <div class="rd-msgs">
              <p class="rd-msg me">{{ p.contents }}</p>
              <p v-if="aiMessage" class="rd-msg ai">{{ aiMessage }}</p>
            </div>
            <p v-if="costLine && !decision" class="rd-costline">
              <span class="k">비용 영향</span><b class="rd-en">{{ costLine.big }}</b><span v-if="costLine.sub" class="sub rd-en">{{ costLine.sub }}</span>
              <button type="button" class="rd-jump" @click="jumpCost">자세히</button>
            </p>
            <div v-if="proposal && (!isRequester || !guidanceComplete)" class="rd-proposal">
              <p class="rd-proposal-k">{{ guidanceComplete ? '안내 내용' : 'AI 제안' }}</p>
              <p class="rd-proposal-body">{{ proposal }}</p>
            </div>
          </section>


          <section v-if="evidence.facts.length || docs.length" id="ev-top" class="rd-card" aria-labelledby="rd-bs">
            <h2 id="rd-bs">{{ showChecks || checks.length ? '판단 근거' : '규정 원문' }} <span class="rd-only">승인자에게만 보여요</span></h2>
            <p v-if="who && checks.length" class="rd-who">요청자 <b>{{ who }}</b></p>
            <dl v-if="evidence.facts.length && !checks.length" class="rd-facts-dl">
              <template v-for="f in evidence.facts" :key="f.k"><dt>{{ f.k }}</dt><dd>{{ f.v }}</dd></template>
            </dl>
            <ul v-if="checks.length && showChecks" class="rd-checks" aria-label="규칙이 확인한 조건">
              <li v-for="c in checks" :key="c.text" :class="c.info ? 'ck-info' : c.ok ? 'ck-ok' : 'ck-no'">
                <span class="rd-ck-ic" aria-hidden="true">{{ c.info ? '' : c.ok ? '✓' : '✕' }}</span>
                <span class="rd-ck-t"><span class="sr-only">{{ c.info ? '참고' : c.ok ? '충족' : '미충족' }}: </span>{{ c.text }}<span v-if="c.detail" class="rd-ck-d rd-en">{{ c.detail }}</span></span>
                <button v-if="c.ref" type="button" class="rd-ck-ref" @click="jumpTo(c.ref)">원문 <span class="rd-en">{{ c.ref }}</span></button>
              </li>
            </ul>
            <details v-if="checks.length && !showChecks" class="rd-checks-fold">
              <summary>충족한 조건 {{ checks.filter(c => c.ok && !c.info).length }}개 <em>펼쳐 보기</em><svg class="rd-doc-chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg></summary>
              <ul class="rd-checks" aria-label="규칙이 확인한 조건">
                <li v-for="c in checks" :key="c.text" :class="c.info ? 'ck-info' : c.ok ? 'ck-ok' : 'ck-no'">
                  <span class="rd-ck-ic" aria-hidden="true">{{ c.info ? '' : c.ok ? '✓' : '✕' }}</span>
                  <span class="rd-ck-t"><span class="sr-only">{{ c.info ? '참고' : c.ok ? '충족' : '미충족' }}: </span>{{ c.text }}<span v-if="c.detail" class="rd-ck-d rd-en">{{ c.detail }}</span></span>
                  <button v-if="c.ref" type="button" class="rd-ck-ref" @click="jumpTo(c.ref)">원문 <span class="rd-en">{{ c.ref }}</span></button>
                </li>
              </ul>
            </details>
            <!-- 규정 원문: 기본은 접어 둔다. 회사 권한표 → 사내 규정 → 공식 도움말 순. -->
            <div v-if="docs.length" class="rd-docs">
              <p v-if="showChecks" class="rd-docs-k">규정 원문 <span>{{ docs.length }}건</span><em>필요할 때만 펼쳐 보세요</em></p>
              <p v-else class="rd-docs-k">규정 원문 <span>{{ docs.length }}건</span><em>요약의 근거예요. 필요할 때만 펼쳐 보세요</em></p>
              <template v-for="(d, di) in docs" :key="d.id">
                <p v-if="di === 0 || docs[di - 1].group !== d.group" class="rd-grp">{{ GROUP_LABEL[d.group] }}</p>
                <details :id="`ev-${d.id}`" class="rd-doc" :class="{ flash: flashDoc === d.id }" :open="openDocs.has(d.id)"
                  @toggle="onToggle(d.id, $event)">
                  <summary>
                    <span class="rd-doc-t">{{ d.title || d.id }}</span>
                    <span v-if="d.title" class="rd-doc-id rd-en">{{ d.id }}</span>
                    <span v-if="d.articles.length" class="rd-doc-n">조항 {{ d.articles.length }}개</span>
                    <svg class="rd-doc-chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                  </summary>
                  <ol v-if="d.articles.length" class="rd-arts">
                    <li v-for="a in d.articles" :key="a.label + a.text">
                      <span class="rd-art-no">{{ a.label }}</span>
                      <div><b v-if="a.heading">{{ a.heading }}</b><p>{{ a.text }}</p></div>
                    </li>
                  </ol>
                  <div v-for="(t, ti) in d.tables" :key="ti" class="rd-tbl-wrap">
                    <table class="rd-tbl">
                      <thead><tr><th v-for="(h, hi) in t.head" :key="hi" :class="{ hit: hi === t.hitCol }">{{ h }}<span v-if="hi === t.hitCol" class="rd-me">요청자</span></th></tr></thead>
                      <tbody>
                        <tr v-for="(r, ri) in (t.hitRows.length && !openTables.has(d.id + ti) ? t.rows.filter((_, i) => t.hitRows.includes(i)) : t.rows)" :key="ri"
                          :class="{ hit: t.hitRows.length && openTables.has(d.id + ti) && t.hitRows.includes(t.rows.indexOf(r)) }">
                          <td v-for="(c, ci) in r" :key="ci" :class="{ hit: ci === t.hitCol }">{{ c }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <button v-if="t.hitRows.length && t.hitRows.length < t.rows.length" type="button" class="rd-tbl-more" @click="toggleTable(d.id + ti)">
                      {{ openTables.has(d.id + ti) ? `${platform?.label ?? '이 플랫폼'} 행만 보기` : `표 전체 보기 (${t.rows.length}행)` }}
                    </button>
                  </div>
                  <p v-for="(n, ni) in d.notes" :key="ni" class="rd-doc-note">{{ n }}</p>
                </details>
              </template>
            </div>
          </section>

          <div v-if="cost" id="cost-card" class="rd-anchor"><CostImpactCard :impact="cost.impact" :mock="cost.mock" /></div>

          <!-- 진행 기록과 요청 기록을 하나로. 번호 · 시각 같은 세부는 접어 둔다. -->
          <section class="rd-card" aria-labelledby="rd-ev" aria-live="polite">
            <div class="rd-card-head">
              <h2 id="rd-ev">처리 기록</h2>
              <span class="rd-id">요청 번호 <span class="rd-en">{{ shortId }}</span>
                <button type="button" class="rd-copy" @click="copyId">{{ copied ? '복사됨' : '전체 복사' }}</button></span>
            </div>
            <ol v-if="events.length" class="rd-events">
              <li v-for="(e, i) in events" :key="i" :class="{ last: i === events.length - 1 && !isTerminal(p.status) }">
                <span class="rd-mark" aria-hidden="true">{{ i === events.length - 1 && !isTerminal(p.status) ? '' : '✓' }}</span>
                <span class="rd-ev-text">{{ e.text }}</span>
                <span class="rd-ev-at rd-en">{{ shortWhen(e.at) }}</span>
              </li>
            </ol>
            <details class="rd-rec">
              <summary>시각 자세히</summary>
              <dl>
                <template v-for="r in record" :key="r.k"><dt>{{ r.k }}</dt><dd>{{ r.v }}</dd></template>
              </dl>
            </details>
          </section>



        </div>

        <aside class="rd-side">
          <section v-if="canDecide" class="rd-approve" aria-labelledby="rd-ap">
            <h2 id="rd-ap">승인 요청</h2>
            <dl>
              <dt>요청자</dt><dd>{{ p.requester_name }} <span class="rd-en">{{ p.employee_no }}</span></dd>
              <dt>권한</dt><dd><span class="rd-chip" :style="{ background: platform.soft, color: platform.color }"><strong>{{ platform.label }}</strong> · {{ roleKo ?? p.requested_role }}</span>
                <span class="rd-code-sm rd-en"><template v-if="resourceName">{{ resourceName }} · </template>{{ p.requested_role }}</span></dd>
              <template v-if="rules.length"><dt>근거</dt><dd>
                <button type="button" class="rd-jump" :class="{ bad: failed }" @click="jumpTo()">
                  {{ failed ? `조건 ${failed}개 미충족` : `조건 ${rules.length}개 모두 충족` }}
                </button>
              </dd></template>
              <template v-else-if="docs.length"><dt>근거</dt><dd class="rd-jumps">
                <button v-for="d in docs.slice(0, 4)" :key="d.id" type="button" class="rd-jump rd-en" :title="d.title" @click="jumpTo(d.id)">{{ d.id }}</button>
                <button v-if="docs.length > 4" type="button" class="rd-jump more" @click="jumpTo()">외 {{ docs.length - 4 }}</button>
              </dd></template>
            </dl>
            <p v-if="isMidStep(p)" class="rd-ap-note"><strong>승인하면</strong> {{ p.current_step! + 1 }}단계 승인자에게 넘어가요. 모든 단계가 승인되면 부여돼요.</p>
            <p v-else class="rd-ap-note"><strong>승인하면</strong> 이 권한이 바로 부여되고, 다시 조회해 반영을 확인한 뒤 {{ p.requester_name }} 님에게 결과를 보여줘요.</p>

            <template v-if="!rejecting">
              <button v-if="!memoOpen" type="button" class="rd-link" @click="memoOpen = true">+ 메모 남기기 <span>(선택)</span></button>
              <div v-else>
                <label for="rd-memo" class="rd-label">승인 메모 <span>(선택 · {{ p.requester_name }} 님에게 보여요)</span></label>
                <input id="rd-memo" v-model="memo" class="rd-input" maxlength="200" placeholder="예: 이번 분기까지만 쓰고 회수 요청할게요">
              </div>
              <div class="rd-ap-actions">
                <button type="button" class="rd-ok-btn" :aria-disabled="deciding" @click="decide(true)">{{ deciding ? '보내는 중…' : '승인' }}</button>
                <button type="button" class="rd-no-btn" :disabled="deciding" @click="rejecting = true">거절</button>
              </div>
            </template>
            <div v-else class="rd-reject">
              <p class="rd-reject-h">{{ isV2() ? '거절 · 보류 사유' : '거절 사유' }} <span>필수 · {{ p.requester_name }} 님에게 그대로 보여요</span></p>
              <div role="group" aria-label="자주 쓰는 사유" class="rd-chips">
                <button v-for="t in REJECT_CHIPS" :key="t" type="button" class="rd-rchip" :aria-pressed="rejPick === t" @click="pickChip(t)">{{ t }}</button>
              </div>
              <label for="rd-rej" class="rd-sr">거절 사유 직접 입력</label>
              <textarea id="rd-rej" v-model="rejText" rows="2" maxlength="200" class="rd-input" placeholder="직접 입력하거나, 고른 사유에 덧붙여 주세요" @input="rejErr = false" />
              <p v-if="rejErr" class="rd-err" role="alert">사유를 고르거나 적어 주세요</p>
              <div class="rd-ap-actions">
                <button type="button" class="rd-send-no" :class="{ on: rejReason && !deciding }" :aria-disabled="!rejReason || deciding" @click="decide(false)">{{ deciding ? '보내는 중…' : '거절 보내기' }}</button>
                <button v-if="isV2()" type="button" class="rd-no-btn" :aria-disabled="!rejReason || deciding" @click="decide(false, true)">보류로 보내기</button>
                <button type="button" class="rd-link muted" @click="cancelReject">취소</button>
              </div>
            </div>
            <p v-if="decideError" class="rd-err" role="alert">{{ decideError }}</p>
          </section>
          <section v-if="canResume" class="rd-approve" aria-labelledby="rd-rs">
            <h2 id="rd-rs">다시 분석</h2>
            <p class="rd-ap-note">예산 · 규정 조건이 바뀌었다면 최신 조건으로 판단안을 다시 만들어요.</p>
            <div class="rd-ap-actions"><button type="button" class="rd-ok-btn" :aria-disabled="resuming" @click="askResume">{{ resuming ? '요청 중…' : '최신 조건으로 다시 분석' }}</button></div>
            <p v-if="decideError" class="rd-err" role="alert">{{ decideError }}</p>
          </section>

          <section v-else-if="['RECEIVED', 'DIAGNOSING', 'EXECUTING', 'WAITING_APPROVAL'].includes(p.status)" class="rd-progress">
            <h2>{{ p.status === 'WAITING_APPROVAL' ? '승인을 기다리고 있어요' : p.status === 'EXECUTING' ? '권한을 넣고 있어요' : '판단안을 만들고 있어요' }}</h2>
            <p>{{ p.status === 'WAITING_APPROVAL' ? (p.total_steps ?? 0) > 1 ? '규정 근거와 예산 영향을 정리한 판단안을 승인자에게 올렸어요. 모든 단계가 승인되면 바로 부여돼요.' : '규정 근거와 예산 영향을 정리한 판단안을 승인자에게 올렸어요. 승인되면 바로 부여돼요.'
              : p.status === 'EXECUTING' ? '부여한 뒤 다시 조회해 반영됐는지 확인해요.'
              : '규정 근거와 예산 영향을 정리해서 승인자에게 올려요.' }}</p>
            <p v-if="isRequester" class="rd-todo rd-todo-plain">이 화면을 닫아도 계속 진행돼요. 결과는 홈의 '내 요청'에서 확인할 수 있어요</p>
          </section>

          <section v-if="!isRequester && p.decided_at" class="rd-decided" :class="p.status === 'REJECTED' ? 'no' : 'yes'">
            <p class="rd-decided-h">{{ p.status === 'REJECTED' ? '거절함' : '승인함' }} · {{ shortWhen(p.decided_at) }}</p>
            <p v-if="p.decision_reason" class="rd-decided-memo"><strong>{{ p.status === 'REJECTED' ? '사유' : '메모' }}</strong> {{ p.decision_reason }}</p>
          </section>

          <!-- 위: 승인자용 안내 · 아래: 요청자용 안내. 승인자가 직접 결정한 건 결정 카드에 이미 보인다. -->
          <section v-if="aprNotice" class="rd-notice" :class="`n-${aprNotice.tone}`" aria-labelledby="rd-ant">
            <h2 id="rd-ant">{{ aprNotice.title }}</h2>
            <p class="rd-todo rd-todo-plain">{{ aprNotice.body }}</p>
            <RouterLink :to="back" class="rd-cta">승인함으로 돌아가기</RouterLink>
          </section>

          <!-- 요청자 안내 카드: 아이콘 + 굵은 제목 + 이유 한 줄 → 다음에 할 일 → 버튼. 한 번에 위에서 아래로 읽히게 한다. -->
          <section v-if="notice" class="rd-notice" :class="`n-${notice.tone}`" aria-labelledby="rd-nt">
            <div class="rd-nt-top">
              <span class="rd-nt-ic" aria-hidden="true">
                <svg v-if="notice.tone === 'bad'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" /><path d="M15 9l-6 6M9 9l6 6" /></svg>
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17h.01" /></svg>
              </span>
              <div class="rd-nt-txt">
                <h2 id="rd-nt">{{ notice.title }}</h2>
                <p v-if="notice.why && isRequester" class="rd-nt-why">{{ notice.why }}</p>
              </div>
            </div>
            <div v-if="notice.memo && isRequester" class="rd-memo"><p class="k">승인자 메모</p><p>{{ notice.memo }}</p></div>
            <div v-if="isRequester" class="rd-todo">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              <div><p class="k">{{ notice.nextLabel }}</p><p>{{ notice.next }}</p></div>
            </div>
            <div class="rd-nt-act">
              <RouterLink v-if="isRequester && notice.resend" :to="{ path: '/', query: { platform: p.platform, text: p.contents } }" class="rd-cta rd-cta-main">이름 넣어 다시 보내기</RouterLink>
              <RouterLink :to="back" class="rd-cta">{{ isRequester ? '내 요청으로 돌아가기' : '승인함으로 돌아가기' }}</RouterLink>
            </div>
          </section>

          <section v-if="p.status === 'DONE'" class="rd-success">
            <!-- 부여 완료 · 이미 보유 · 안내 완료를 같은 '열렸어요'로 쓰지 않는다. -->
            <h2>{{ isAlreadyHas(p) ? '이미 권한이 있어요' : guidanceComplete ? '안내를 확인해 주세요' : '권한이 열렸어요' }}</h2>
            <p>{{ isAlreadyHas(p) ? `${platform.label}에서 조회해 보니 필요한 권한을 이미 갖고 있어요. 바꾼 것은 없어요. 그래도 안 되면 로그아웃 후 다시 로그인해 보세요.`
              : guidanceComplete ? '권한을 바꾸지 않고 방법을 안내했어요. 왼쪽 안내 내용을 확인해 주세요.'
              : `${platform.label}에서 다시 조회해 반영을 확인했어요. 지금 바로 쓸 수 있어요.` }}</p>
          </section>

        </aside>
      </div>
    </template>
    <p v-if="toast" class="rd-toast" role="status">{{ toast }}</p>
  </AppShell>
</template>

<style scoped>
.rd-top { margin: 28px 0 20px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.rd-back { font-size: 14px; font-weight: 600; color: var(--uo-primary); text-decoration: none; }
.rd-top h1 { margin: 10px 0 0; font-size: 30px; font-weight: 700; letter-spacing: -0.01em; }
.rd-meta { margin: 8px 0 0; font-size: 15px; color: var(--uo-ink-2); }
.rd-meta b { font-weight: 700; color: var(--uo-ink); }
.rd-codes { margin: 4px 0 0; font-size: 12px; color: var(--uo-muted); letter-spacing: 0.01em; }
.rd-code-sm { display: block; margin-top: 4px; font-size: 12px; color: var(--uo-muted); }
.rd-perm-role .rd-code-sm { display: inline; margin: 0 0 0 6px; }
.rd-en { font-family: var(--uo-font-en); }
.rd-badge { font-size: 15px; font-weight: 700; padding: 8px 18px; border-radius: 999px; white-space: nowrap; }
.rd-badge.sm { font-size: 12px; padding: 3px 9px; }
.run { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.warn { background: var(--uo-warn-bg); color: var(--uo-warn); }
.review { background: var(--uo-review-bg); color: var(--uo-review); }
.ok { background: var(--uo-ok-bg); color: var(--uo-ok); }
.bad { background: var(--uo-bad-bg); color: var(--uo-bad); }
.todo { background: #F0F1F5; color: #4A5068; }
.rd-state { background: #fff; border: 1px dashed var(--uo-line-strong); border-radius: 20px; padding: 28px; color: var(--uo-muted); }
.rd-warn { margin: 0 0 12px; color: var(--uo-warn); font-weight: 600; }
.rd-cols { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.rd-main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 20px; }
.rd-side { flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 20px; }
/* 넓은 화면에서는 근거를 읽으며 내려가도 승인 상자가 옆에 남아 있게 한다. */
@media (min-width: 1100px) { .rd-side { position: sticky; top: 24px; max-height: calc(100vh - 48px); overflow-y: auto; overscroll-behavior: contain; } }
.rd-card { background: #fff; border: 1px solid var(--uo-line); border-radius: 20px; padding: 24px; }
.rd-card h2, .rd-side h2 { margin: 0 0 14px; font-size: 18px; font-weight: 700; }
.rd-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px 16px; flex-wrap: wrap; margin-bottom: 18px; }
.rd-card .rd-card-head h2 { margin: 0; }
.rd-facts { display: flex; flex-wrap: wrap; gap: 6px; }
.rd-fact { font-size: 13px; font-weight: 600; padding: 5px 10px; border-radius: 999px; background: #F0F1F5; color: var(--uo-ink-2); }
.rd-msgs { display: flex; flex-direction: column; gap: 12px; }
.rd-msg { margin: 0; max-width: 82%; padding: 12px 16px; font-size: 15px; line-height: 1.7; white-space: pre-line; }
.rd-msg.me { align-self: flex-end; background: var(--uo-primary); color: #fff; border-radius: 16px 16px 4px 16px; }
.rd-msg.ai { align-self: flex-start; background: #F1F2F8; color: var(--uo-ink); border-radius: 16px 16px 16px 4px; }
.rd-proposal { margin-top: 16px; padding: 14px 16px; border-radius: 14px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 100%); border: 1px solid #C9CEF5; }
.rd-proposal p { margin: 0; font-size: 15px; line-height: 1.65; }
.rd-proposal-body { white-space: pre-wrap; overflow-wrap: anywhere; }
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
.rd-rec { border: 0; margin: 12px 0 0; padding: 0; }
.rd-rec summary { font-size: 13px; font-weight: 600; color: var(--uo-muted); cursor: pointer; }
.rd-id { font-size: 13px; color: var(--uo-muted); display: inline-flex; align-items: center; gap: 6px; }
.rd-id .rd-en { color: var(--uo-ink); font-weight: 600; }
.rd-copy { border: 1px solid var(--uo-line); background: #fff; border-radius: 6px; padding: 1px 8px; font-size: 12px; color: var(--uo-ink-2); cursor: pointer; }
.rd-copy:focus-visible { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
.rd-anchor { scroll-margin-top: 24px; }
.rd-sum { border-left: 6px solid var(--uo-ok, #1A7340); display: flex; flex-direction: column; gap: 8px; }
.rd-sum.review { border-left-color: var(--uo-review); }
.rd-sum.done { border-left-color: var(--uo-primary); }
.rd-sum.done .rd-sum-badge { background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.rd-sum.done .rd-sum-h { color: var(--uo-ink); }
.rd-toast { position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%); margin: 0; padding: 12px 20px; border-radius: 12px; background: var(--uo-ink); color: #fff; font-size: 14px; font-weight: 600; z-index: 40; max-width: calc(100% - 32px); }
.rd-sum-badge { align-self: flex-start; font-size: 13px; font-weight: 700; border-radius: 999px; padding: 3px 12px; background: var(--uo-ok-bg, #E6F4EC); color: var(--uo-ok, #1A7340); }
.rd-sum.review .rd-sum-badge { background: var(--uo-review-bg); color: var(--uo-review); }
.rd-sum-h { margin: 4px 0 0; font-size: 22px; font-weight: 800; line-height: 1.4; letter-spacing: -0.01em; }
.rd-sum-sub { margin: 0; font-size: 14px; color: var(--uo-muted); }
.rd-sum-nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin: 8px 0; }
.rd-sum-num { background: var(--uo-bg, #F6F7FC); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 2px; }
.rd-sum-num b { font-size: 20px; font-weight: 800; color: var(--uo-primary-ink); letter-spacing: -0.02em; }
.rd-sum-num span { font-size: 12px; color: var(--uo-muted); }
.rd-sum-k { margin: 6px 0 0; font-size: 13px; font-weight: 700; color: var(--uo-muted); }
.rd-sum-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.rd-sum-checks li { display: flex; align-items: flex-start; gap: 10px; font-size: 15px; }
.rd-sum-checks .rd-ck-ref { margin-left: auto; }
.rd-sum-steps { list-style: none; margin: 8px 0 0; padding: 0; display: flex; gap: 6px; }
.rd-sum-steps li { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 4px; border-radius: 10px; background: var(--uo-bg, #F6F7FC); font-size: 12px; color: var(--uo-muted); text-align: center; }
.rd-sum-steps li b { font-size: 13px; color: var(--uo-ink-2); }
.rd-sum-steps li.on { background: var(--uo-warn-bg, #FDF0E4); color: var(--uo-warn, #9A4A08); }
.rd-sum-steps li.done { background: var(--uo-ok-bg, #E6F4EC); color: var(--uo-ok, #1A7340); }
.rd-sum-steps li.bad { background: var(--uo-bad-bg, #FDECEC); color: var(--uo-bad); }
.rd-sum-more { align-self: flex-start; }
.rd-costline { margin: 14px 0 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; font-size: 14px; }
.rd-costline .k { color: var(--uo-muted); }
.rd-costline b { font-size: 16px; color: var(--uo-primary-ink); }
.rd-costline .sub { color: var(--uo-ink-2); }
.rd-costline .rd-jump { margin-left: auto; }
.rd-rec dl { margin: 12px 0 0; display: grid; grid-template-columns: 120px minmax(0, 1fr); row-gap: 10px; font-size: 14px; }
.rd-rec dt { color: var(--uo-muted); }
.rd-rec dd { margin: 0; word-break: break-all; }
.rd-progress { border-radius: 24px; padding: 24px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 60%, #F7F3FF 100%); border: 1px solid var(--uo-primary-ink); display: flex; flex-direction: column; gap: 12px; }
.rd-progress h2 { margin: 0; font-size: 20px; color: var(--uo-primary-ink); }
.rd-progress > p { margin: 0; font-size: 15px; line-height: 1.65; }
.rd-todo { background: #fff; border-radius: 12px; padding: 14px 16px; }
.rd-notice .rd-todo { display: flex; gap: 10px; align-items: flex-start; background: var(--nbg); border: 0; }
.rd-notice .rd-todo > svg { flex: 0 0 16px; margin-top: 3px; color: var(--nfg); }
.rd-todo p, .rd-memo p { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.55; }
.rd-todo-plain { margin: 0; font-size: 15px; font-weight: 500; line-height: 1.55; color: var(--uo-ink-2); }
.rd-todo .k, .rd-memo .k { margin-bottom: 4px; font-size: 13px; color: var(--uo-muted); }
.rd-notice { border-radius: 20px; padding: 22px; display: flex; flex-direction: column; gap: 14px; background: #fff; border: 1px solid var(--uo-line); box-shadow: 0 1px 2px rgba(20,26,51,.04); }
.rd-nt-top { display: flex; gap: 14px; align-items: flex-start; }
.rd-nt-ic { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center; background: var(--nbg); color: var(--nfg); }
.rd-nt-txt { min-width: 0; }
.rd-nt-why { margin: 6px 0 0; font-size: 14px; line-height: 1.55; color: var(--uo-muted); }
.rd-nt-act { display: flex; flex-direction: column; gap: 8px; }
.rd-notice.n-bad { --nfg: var(--uo-bad); --nbg: var(--uo-bad-bg); }
.rd-notice.n-review { --nfg: var(--uo-review); --nbg: var(--uo-review-bg); }
.rd-notice h2 { margin: 0; font-size: 18px; line-height: 1.4; color: var(--uo-ink); }
.rd-memo { background: var(--uo-bg); border-radius: 12px; padding: 12px 14px; }
.rd-memo p:last-child { font-weight: 400; }
.rd-cta { height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; color: var(--nfg); background: #fff; border: 1.5px solid var(--nfg); text-decoration: none; }
.rd-only { margin-left: 8px; font-size: 12px; font-weight: 700; color: #5B3FD6; background: #F1ECFF; border-radius: 999px; padding: 3px 9px; vertical-align: 2px; }
.rd-facts-dl { margin: 0 0 16px; display: grid; grid-template-columns: 140px minmax(0, 1fr); row-gap: 10px; font-size: 15px; }
.rd-facts-dl dt { color: var(--uo-muted); }
.rd-facts-dl dd { margin: 0; font-weight: 600; }
.rd-who { margin: -4px 0 12px; font-size: 14px; color: var(--uo-muted); }
.rd-who b { margin-left: 6px; color: var(--uo-ink); font-weight: 600; }
.rd-checks { list-style: none; margin: 0 0 20px; padding: 0; border: 1px solid var(--uo-line); border-radius: 14px; overflow: hidden; }
.rd-checks li { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-top: 1px solid #F0F2F8; }
.rd-checks li:first-child { border-top: 0; }
.rd-ck-ic { width: 22px; height: 22px; flex: 0 0 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; color: #fff; background: var(--uo-primary); }
.rd-checks li.ck-no { background: var(--uo-bad-bg); }
.rd-checks li.ck-info .rd-ck-ic { background: transparent; border: 2px solid var(--uo-line-strong); width: 12px; height: 12px; flex-basis: 12px; margin: 0 5px; }
.rd-checks li.ck-info .rd-ck-t { font-weight: 500; color: var(--uo-ink-2); }
.rd-checks li.ck-no .rd-ck-ic { background: var(--uo-bad); }
.rd-ck-t { flex: 1; min-width: 0; font-size: 15px; font-weight: 600; color: var(--uo-ink); }
.rd-ck-d { margin-left: 8px; font-size: 13px; font-weight: 500; color: var(--uo-muted); }
.rd-ck-ref { flex: 0 0 auto; border: 0; background: none; padding: 4px 0; font-size: 13px; color: var(--uo-muted); cursor: pointer; }
.rd-ck-ref:hover { color: var(--uo-primary-ink); text-decoration: underline; }
.rd-ck-ref:focus-visible { outline: 2px solid var(--uo-primary); outline-offset: 2px; border-radius: 4px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.rd-checks-fold { margin: 0 0 14px; padding: 0; border: 1px solid var(--uo-line); border-radius: 12px; }
.rd-checks-fold > summary { display: flex; align-items: center; gap: 8px; min-height: 48px; padding: 0 14px; line-height: 1.4; font-size: 14px; font-weight: 700; color: var(--uo-ink); cursor: pointer; list-style: none; }
.rd-checks-fold > summary::-webkit-details-marker { display: none; }
.rd-checks-fold > summary em { font-style: normal; font-weight: 400; color: var(--uo-muted); }
.rd-checks-fold > summary .rd-doc-chev { margin-left: auto; transition: transform .15s; }
.rd-checks-fold[open] > summary .rd-doc-chev { transform: rotate(180deg); }
.rd-checks-fold > .rd-checks { margin: 0; border: 0; border-top: 1px solid var(--uo-line); border-radius: 0 0 12px 12px; }
.rd-docs-k { margin: 0 0 4px; font-size: 13px; font-weight: 700; color: var(--uo-muted); }
.rd-docs-k em { margin-left: 8px; font-style: normal; font-weight: 400; }
.rd-docs-k span { margin-left: 4px; font-weight: 600; color: var(--uo-ink-2); }
.rd-grp { margin: 12px 0 6px; font-size: 12px; font-weight: 600; color: var(--uo-muted); }
.rd-doc { border: 1px solid var(--uo-line); border-radius: 12px; margin: 0 0 6px; padding: 0; background: #fff; overflow: hidden; }
.rd-doc[open] { box-shadow: 0 1px 2px rgba(20,26,51,.05); }
.rd-doc { scroll-margin-top: 24px; transition: box-shadow .3s, border-color .3s; }
.rd-doc.flash { border-color: var(--uo-primary); box-shadow: 0 0 0 4px var(--uo-primary-soft); }
#ev-top { scroll-margin-top: 24px; }
.rd-jumps { display: flex; flex-wrap: wrap; gap: 6px; }
.rd-jump { border: 1px solid #D5D9EA; background: #fff; color: var(--uo-primary-ink); border-radius: 8px; padding: 2px 9px; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: background-color .15s, border-color .15s; }
.rd-jump::after { content: '↓'; font-size: 11px; color: var(--uo-muted); }
.rd-jump.more { color: var(--uo-ink-2); font-family: var(--uo-font); }
.rd-jump.bad { color: var(--uo-bad); border-color: #F1C9C9; }
.rd-jump:hover { background: var(--uo-primary-soft); border-color: #B9C0E8; }
.rd-jump:focus-visible { outline: 2px solid var(--uo-primary); outline-offset: 2px; }
.rd-doc summary { list-style: none; cursor: pointer; display: flex; gap: 10px; align-items: center; padding: 11px 14px; }
.rd-doc summary::-webkit-details-marker { display: none; }
.rd-doc summary:hover { background: #FAFBFE; }
.rd-doc summary:focus-visible { outline: 2px solid var(--uo-primary); outline-offset: -2px; }
.rd-doc-id { flex: 0 0 auto; font-size: 12px; color: var(--uo-muted); }
.rd-doc-t { flex: 1; min-width: 0; font-size: 14px; font-weight: 600; color: var(--uo-ink); }
.rd-doc-n { font-size: 12px; color: var(--uo-muted); white-space: nowrap; }
.rd-doc-chev { color: var(--uo-muted); transition: transform .15s; }
.rd-doc[open] .rd-doc-chev { transform: rotate(180deg); }
.rd-arts { list-style: none; margin: 0; padding: 4px 14px 12px; display: flex; flex-direction: column; }
.rd-arts li { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 10px; padding: 10px 0; border-top: 1px solid #F0F2F8; }
.rd-arts li:first-child { border-top: 0; }
.rd-art-no { font-size: 12px; font-weight: 700; color: var(--uo-ink-2); background: var(--uo-bg); border-radius: 6px; padding: 3px 0; text-align: center; height: fit-content; }
.rd-arts b { display: block; font-size: 14px; font-weight: 700; color: var(--uo-ink); }
.rd-arts p { margin: 2px 0 0; font-size: 14px; line-height: 1.6; color: var(--uo-ink-2); }
.rd-tbl-wrap { padding: 4px 14px 12px; overflow-x: auto; }
.rd-tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; border: 1px solid var(--uo-line); border-radius: 10px; overflow: hidden; }
.rd-tbl th { text-align: left; font-weight: 600; color: var(--uo-muted); background: #FAFBFE; padding: 8px 10px; border-bottom: 1px solid var(--uo-line); white-space: nowrap; }
.rd-tbl td { padding: 8px 10px; border-bottom: 1px solid #F0F2F8; color: var(--uo-ink-2); }
.rd-tbl tbody tr:last-child td { border-bottom: 0; }
.rd-tbl th.hit, .rd-tbl td.hit { background: var(--uo-primary-soft); color: var(--uo-primary-ink); font-weight: 700; }
.rd-tbl tr.hit td { background: #FAFAFF; }
.rd-me { margin-left: 6px; font-size: 10px; font-weight: 700; color: #fff; background: var(--uo-primary); border-radius: 999px; padding: 1px 6px; vertical-align: 1px; }
.rd-tbl-more { margin-top: 8px; border: 0; background: none; padding: 2px 0; font: inherit; font-size: 13px; font-weight: 600; color: var(--uo-primary-ink); cursor: pointer; }
.rd-doc-note { margin: 0; padding: 0 14px 12px; font-size: 13px; line-height: 1.6; color: var(--uo-muted); }
.rd-perm-target { margin: 14px 0 0; font-size: 19px; font-weight: 700; word-break: keep-all; }
.rd-perm-target + .rd-perm-role { margin-top: 6px; }
.rd-approve { border-radius: 24px; padding: 24px; background: linear-gradient(100deg, #EEF0FF 0%, #F2EDFF 60%, #F7F3FF 100%); border: 1px solid var(--uo-primary-ink); box-shadow: 0 10px 34px rgba(59,75,216,0.12); display: flex; flex-direction: column; gap: 14px; }
.rd-approve h2 { margin: 0; }
.rd-approve dl { margin: 0; display: grid; grid-template-columns: 72px minmax(0, 1fr); row-gap: 10px; font-size: 14px; }
.rd-approve dt { color: var(--uo-muted); }
.rd-approve dd { margin: 0; word-break: break-all; }
.rd-chip { display: inline-block; font-size: 13px; padding: 4px 8px; border-radius: 6px; }
.rd-ap-note { margin: 0; font-size: 14px; line-height: 1.6; }
.rd-link { align-self: flex-start; padding: 0; border: 0; background: none; font: inherit; font-size: 14px; font-weight: 600; color: var(--uo-primary); cursor: pointer; min-height: 32px; }
.rd-link span { font-weight: 400; color: var(--uo-muted); }
.rd-link.muted { color: var(--uo-muted); align-self: center; }
.rd-label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: var(--uo-ink-2); }
.rd-label span { font-weight: 400; color: var(--uo-muted); }
.rd-input { width: 100%; min-height: 44px; padding: 10px 12px; border: 1px solid var(--uo-line-strong); border-radius: 12px; background: #fff; font: inherit; font-size: 14px; line-height: 1.5; color: var(--uo-ink); box-sizing: border-box; resize: vertical; }
.rd-ap-actions { display: flex; gap: 10px; align-items: center; }
.rd-ok-btn { flex: 1; height: 48px; border: 0; border-radius: 12px; font: inherit; font-size: 15px; font-weight: 700; color: #fff; background: var(--uo-gradient); cursor: pointer; }
.rd-no-btn { height: 48px; padding: 0 18px; border-radius: 12px; font: inherit; font-size: 15px; font-weight: 600; color: var(--uo-bad); background: #fff; border: 1px solid #F0C9CF; cursor: pointer; }
.rd-reject { background: #fff; border: 1px solid #F0C9CF; border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.rd-reject-h { margin: 0; font-size: 15px; font-weight: 700; color: var(--uo-bad); }
.rd-reject-h span { font-size: 13px; font-weight: 400; color: var(--uo-muted); }
.rd-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.rd-rchip { min-height: 36px; padding: 0 12px; border-radius: 999px; font: inherit; font-size: 13px; font-weight: 600; background: #fff; color: var(--uo-ink-2); border: 1px solid #D5D9EA; cursor: pointer; }
.rd-rchip[aria-pressed="true"] { background: var(--uo-bad-bg); color: var(--uo-bad); border-color: var(--uo-bad); }
.rd-send-no { flex: 1; height: 46px; border: 0; border-radius: 12px; font: inherit; font-size: 15px; font-weight: 700; color: #fff; background: #D9A3AB; cursor: not-allowed; }
.rd-send-no.on { background: var(--uo-bad); cursor: pointer; }
.rd-err { margin: 0; font-size: 14px; font-weight: 600; line-height: 1.5; color: var(--uo-bad); }
.rd-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.rd-decided { border-radius: 20px; padding: 18px 20px; }
.rd-decided.yes { background: var(--uo-ok-bg); border: 1px solid #BFE3CC; --dfg: var(--uo-ok); }
.rd-decided.no { background: var(--uo-bad-bg); border: 1px solid #F0C9CF; --dfg: var(--uo-bad); }
.rd-decided-h { margin: 0; font-size: 15px; font-weight: 700; color: var(--dfg); }
.rd-decided-memo { margin: 8px 0 0; font-size: 14px; line-height: 1.6; background: rgba(255,255,255,0.8); border-radius: 10px; padding: 10px 12px; }
.rd-decided-memo strong { color: var(--uo-ink-2); margin-right: 4px; }
.rd-cta-main { color: #fff; background: var(--nfg); }
.rd-success { border-radius: 20px; padding: 24px; background: var(--uo-ok-bg); border: 1px solid #BFE3CC; }
.rd-success h2 { margin: 0 0 10px; font-size: 20px; color: var(--uo-ok); }
.rd-success p { margin: 0; font-size: 15px; line-height: 1.65; }
@keyframes rd-spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) { .rd-top h1 { font-size: 24px; } .rd-msg { max-width: 92%; } }
@media (prefers-reduced-motion: reduce) { .last .rd-mark { animation: none; } }
</style>
