<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError, type Problem } from '../api'
import AppShell from '../components/AppShell.vue'
import StageBar from '../components/StageBar.vue'
import { PLATFORMS } from '../lib/platforms'
import { usePolling } from '../lib/polling'
import { aiMessageOf, approverEventsOf, approverNoticeOf, approverSummaryOf, evidenceOf, noticeOf, proposalOf, requesterEventsOf, REJECT_CHIPS, stagesOf, summaryOf } from '../lib/requestView'
import { isGuidanceComplete, isTerminal, needsRefresh, statusOf } from '../lib/status'
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
    item.value = await api<Problem>(`/problems/${encodeURIComponent(id)}`)
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
const platform = computed(() => p.value ? PLATFORMS[p.value.platform] : null)
const stages = computed(() => p.value ? stagesOf(p.value) : [])
const summary = computed(() => !p.value ? '' : isRequester.value ? summaryOf(p.value) : approverSummaryOf(p.value))
// 안내 성공은 요청자도 진단을 본다. 실제 검토 필요 · 거절의 판단 근거는 승인자에게만 표시한다.
const aiMessage = computed(() => !p.value ? null : isRequester.value ? aiMessageOf(p.value) : p.value.diagnosis?.trim() || null)
// 승인자는 plan의 자원 이름(resource_key)까지 받는다. 요청자 응답에는 plan이 없다.
const resourceName = computed(() => (!isRequester.value && p.value?.plan?.resource_key) || '')
const proposal = computed(() => p.value && platform.value ? proposalOf(p.value, resourceName.value || platform.value.label) : null)
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
    { k: '결정 시각', v: isGuidanceComplete(x) ? '해당 없음' : x.decided_at ? shortWhen(x.decided_at) : '아직 없음' },
    { k: '반영 확인', v: isGuidanceComplete(x) ? '해당 없음' : x.verification_ok === true ? '✓ 확인됨' : x.verification_ok === false ? '✕ 반영 안 됨' : '아직 없음' },
  ]
})

/* ---------- 승인 카드 (승인자 · 승인 대기일 때만) ---------- */
const canDecide = computed(() => !isRequester.value && p.value?.status === 'WAITING_APPROVAL')
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

async function decide(approved: boolean) {
  const x = p.value
  if (!x || deciding.value) return
  if (!approved && !rejReason.value) { rejErr.value = true; return }
  deciding.value = true
  decideError.value = ''
  try {
    // 승인 카드에 보이는 계획(plan_hash)에 대해서만 결정한다. 그사이 계획이 바뀌면 서버가 409로 막는다.
    await api(`/problems/${encodeURIComponent(x.id)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approved, expectedPlanHash: x.plan_hash, reason: approved ? memo.value.trim() : rejReason.value }),
    })
    rejecting.value = false
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
    { t: '원인과 근거를 확인하세요', d: 'AI가 조회한 요청자 정보와 사내 규정 원문이 왼쪽 판단 근거에 있어요' },
    { t: '승인하거나 거절하세요', d: '승인하면 바로 부여되고 다시 조회해 반영을 확인해요. 거절할 땐 사유가 필요해요' },
  ],
  faqs: [
    { q: '승인 메모 · 거절 사유는 누가 보나요?', a: '요청자에게 그대로 보여요. 판단 근거(규정 · 조회 결과)는 승인자에게만 보여요.' },
    { q: '결정하려는데 내용이 바뀌었다고 나와요', a: '그사이 AI가 계획을 다시 만들었거나 다른 곳에서 처리된 경우예요. 새로 불러온 내용을 확인하고 다시 결정해 주세요.' },
  ],
}
const requesterHelp = {
  howto: [
    { t: '진행 단계를 보세요', d: '권한 변경은 접수 → AI 진단 → 승인 → 권한 부여 → 반영 확인 순서로 진행돼요. 안내 요청은 진단 후 안내 제공으로 완료돼요' },
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
        <h1 v-if="p && platform">{{ platform.label }}<template v-if="resourceName"> · {{ resourceName }}</template><template v-if="p.requested_role"> · {{ p.requested_role }}</template></h1>
        <p v-if="p" class="rd-meta"><span class="rd-en">{{ p.id.slice(0, 8) }}</span> · {{ p.requester_name }}<template v-if="!isRequester"> ({{ p.employee_no }})</template> · {{ shortWhen(p.created_at) }} 요청</p>
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
          <section class="rd-card" aria-labelledby="rd-dg">
            <!-- 플랫폼 · 자원 · 권한은 대화가 아니라 요청 정보라서, 말풍선과 떨어진 제목 줄 오른쪽에 배지로 둔다. -->
            <div class="rd-card-head">
              <h2 id="rd-dg">{{ guidanceComplete && !isRequester ? '요청 내용과 안내' : aiMessage || proposal ? '요청 내용과 AI 진단' : '요청 내용' }}</h2>
              <div class="rd-facts" aria-label="요청 정보">
                <span class="rd-ptag" :style="{ background: platform.soft, color: platform.color }">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="platform.icon" /></svg>{{ platform.label }}
                </span>
                <span v-if="resourceName" class="rd-fact rd-en">{{ resourceName }}</span>
                <span v-if="p.requested_role" class="rd-fact">{{ p.requested_role }}</span>
              </div>
            </div>
            <div class="rd-msgs">
              <p class="rd-msg me">{{ p.contents }}</p>
              <p v-if="aiMessage" class="rd-msg ai">{{ aiMessage }}</p>
            </div>
            <div v-if="proposal && (!isRequester || !guidanceComplete)" class="rd-proposal">
              <p class="rd-proposal-k">{{ guidanceComplete ? '안내 내용' : 'AI 제안' }}</p>
              <p class="rd-proposal-body">{{ proposal }}</p>
            </div>
          </section>

          <section v-if="evidence.facts.length || evidence.docs.length" class="rd-card" aria-labelledby="rd-bs">
            <h2 id="rd-bs">판단 근거 <span class="rd-only">승인자에게만 보여요</span></h2>
            <dl v-if="evidence.facts.length" class="rd-facts-dl">
              <template v-for="f in evidence.facts" :key="f.k"><dt>{{ f.k }}</dt><dd>{{ f.v }}</dd></template>
            </dl>
            <div v-if="evidence.docs.length" class="rd-docs">
              <p class="rd-docs-k">AI가 확인한 규정 원문</p>
              <details v-for="d in evidence.docs" :key="d.id" class="rd-doc">
                <summary><span class="rd-en">{{ d.id }}</span><span v-if="d.parts.some(x => x.article)" class="rd-doc-art">{{ d.parts.map(x => x.article).filter(Boolean).join(' · ') }}</span></summary>
                <p v-for="(x, i) in d.parts" :key="i">{{ x.text }}</p>
              </details>
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
              <h3 v-if="resourceName" class="rd-perm-target rd-en">{{ resourceName }}</h3>
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
          <section v-if="canDecide" class="rd-approve" aria-labelledby="rd-ap">
            <h2 id="rd-ap">승인 요청</h2>
            <dl>
              <dt>요청자</dt><dd>{{ p.requester_name }} <span class="rd-en">{{ p.employee_no }}</span></dd>
              <dt>권한</dt><dd><span class="rd-chip" :style="{ background: platform.soft, color: platform.color }"><strong>{{ platform.label }}</strong><template v-if="resourceName"> · {{ resourceName }}</template> · {{ p.requested_role }}</span></dd>
              <template v-if="evidence.docs.length"><dt>근거</dt><dd class="rd-en">{{ evidence.docs.map(d => d.id).slice(0, 4).join(' · ') }}<template v-if="evidence.docs.length > 4"> 외 {{ evidence.docs.length - 4 }}</template></dd></template>
            </dl>
            <p class="rd-ap-note"><strong>승인하면</strong> 이 권한이 바로 부여되고, 다시 조회해 반영을 확인한 뒤 {{ p.requester_name }} 님에게 결과를 보여줘요.</p>

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
              <p class="rd-reject-h">거절 사유 <span>필수 · {{ p.requester_name }} 님에게 그대로 보여요</span></p>
              <div role="group" aria-label="자주 쓰는 사유" class="rd-chips">
                <button v-for="t in REJECT_CHIPS" :key="t" type="button" class="rd-rchip" :aria-pressed="rejPick === t" @click="pickChip(t)">{{ t }}</button>
              </div>
              <label for="rd-rej" class="rd-sr">거절 사유 직접 입력</label>
              <textarea id="rd-rej" v-model="rejText" rows="2" maxlength="200" class="rd-input" placeholder="직접 입력하거나, 고른 사유에 덧붙여 주세요" @input="rejErr = false" />
              <p v-if="rejErr" class="rd-err" role="alert">사유를 고르거나 적어 주세요</p>
              <div class="rd-ap-actions">
                <button type="button" class="rd-send-no" :class="{ on: rejReason && !deciding }" :aria-disabled="!rejReason || deciding" @click="decide(false)">{{ deciding ? '보내는 중…' : '거절 보내기' }}</button>
                <button type="button" class="rd-link muted" @click="cancelReject">취소</button>
              </div>
            </div>
            <p v-if="decideError" class="rd-err" role="alert">{{ decideError }}</p>
          </section>

          <section v-else-if="['RECEIVED', 'DIAGNOSING', 'EXECUTING', 'WAITING_APPROVAL'].includes(p.status)" class="rd-progress">
            <h2>{{ p.status === 'WAITING_APPROVAL' ? '승인을 기다리고 있어요' : p.status === 'EXECUTING' ? '권한을 넣고 있어요' : '진단 중이에요' }}</h2>
            <p>{{ p.status === 'WAITING_APPROVAL' ? '원인과 규정 근거를 정리해 승인자에게 올렸어요. 승인되면 바로 부여돼요.'
              : p.status === 'EXECUTING' ? '부여한 뒤 다시 조회해 반영됐는지 확인해요.'
              : '끝나면 원인을 정리해서 승인자에게 승인을 요청해요.' }}</p>
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

          <section v-if="notice" class="rd-notice" :class="`n-${notice.tone}`" aria-labelledby="rd-nt">
            <h2 id="rd-nt">{{ notice.title }}</h2>
            <div v-if="notice.memo && isRequester" class="rd-memo"><p class="k">승인자 메모</p><p>{{ notice.memo }}</p></div>
            <div v-if="isRequester" class="rd-todo"><p class="k">{{ notice.nextLabel }}</p><p>{{ notice.next }}</p></div>
            <RouterLink v-if="isRequester && notice.resend" :to="{ path: '/', query: { platform: p.platform, text: p.contents } }" class="rd-cta rd-cta-main">이름 넣어 다시 보내기</RouterLink>
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
.review { background: var(--uo-review-bg); color: var(--uo-review); }
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
.rd-todo-plain { margin: 0; font-size: 15px; font-weight: 500; line-height: 1.55; color: var(--uo-ink-2); }
.rd-todo .k, .rd-memo .k { margin-bottom: 4px; font-size: 13px; color: var(--uo-muted); }
.rd-notice { border-radius: 20px; padding: 24px; display: flex; flex-direction: column; gap: 14px; }
.rd-notice.n-bad { background: var(--uo-bad-bg); border: 1px solid #F0C9CF; --nfg: var(--uo-bad); }
.rd-notice.n-review { background: var(--uo-review-bg); border: 1px solid #F3D2B3; --nfg: var(--uo-review); }
.rd-notice h2 { margin: 0; font-size: 20px; line-height: 1.4; color: var(--nfg); }
.rd-memo { background: rgba(255,255,255,0.75); border-radius: 12px; padding: 12px 14px; }
.rd-memo p:last-child { font-weight: 400; }
.rd-cta { height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; color: var(--nfg); background: #fff; border: 1.5px solid var(--nfg); text-decoration: none; }
.rd-only { margin-left: 8px; font-size: 12px; font-weight: 700; color: #5B3FD6; background: #F1ECFF; border-radius: 999px; padding: 3px 9px; vertical-align: 2px; }
.rd-facts-dl { margin: 0 0 16px; display: grid; grid-template-columns: 140px minmax(0, 1fr); row-gap: 10px; font-size: 15px; }
.rd-facts-dl dt { color: var(--uo-muted); }
.rd-facts-dl dd { margin: 0; font-weight: 600; }
.rd-docs-k { margin: 0 0 8px; font-size: 13px; font-weight: 700; color: var(--uo-muted); }
.rd-doc { border: 0; margin: 0; padding: 12px 0; border-top: 1px solid #EEF0F6; }
.rd-doc summary { cursor: pointer; font-size: 15px; font-weight: 600; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.rd-doc-art { font-size: 13px; font-weight: 500; color: var(--uo-muted); }
.rd-doc p { margin: 10px 0 0; font-size: 14px; line-height: 1.65; color: var(--uo-ink-2); white-space: pre-line; }
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
