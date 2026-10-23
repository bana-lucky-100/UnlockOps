<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api'
import { demoLogin, homeOf, login } from '../session'

const router = useRouter()
const route = useRoute()

// 시연 계정은 서버의 시연 로그인(/auth/demo-login)을 쓴다. 비밀번호를 화면에 하드코딩하지 않는다(#29).
// 화면 이름은 UX 산출물의 페르소나(직원 · 부서장 · IT 권한 관리)에 맞춘다. 로그인 뒤 상단 이름은 서버 시드 이름으로 보일 수 있다.
const accounts = [
  { key: 'EMPLOYEE', loginId: 'p2_a_requester', title: '직원 · 김지성', desc: 'A사 개발팀 사원 · 권한 요청', initial: '지', tag: '요청', tone: 't-blue', cta: '직원으로 로그인' },
  { key: 'ORG_HEAD', loginId: 'p2_a_head', title: '부서장 · 김동빈', desc: 'A사 개발팀 · 1차 승인 · 예산 판단', initial: '동', tag: '1차 승인', tone: 't-violet', cta: '부서장으로 로그인' },
  { key: 'IT_FINAL', loginId: 'p2_a_operator', title: 'IT 권한 관리 · 신형철', desc: 'A사 IT 권한 관리 · 최종 승인 · 회수 점검', initial: '형', tag: '최종 승인', tone: 't-indigo', cta: 'IT 권한 관리자로 로그인' },
] as const
// 다른 회사 · 담당 역할(팀장, IT 총괄, Figma 담당자 등)은 아래 목록에서 고른다.
const demoAccounts = ['a', 'b'].flatMap(company => [
  { role: 'requester', label: '직원' }, { role: 'team_lead', label: '팀장' },
  { role: 'head', label: '부서장' }, { role: 'operator', label: '권한 담당자' },
  { role: 'it_head', label: 'IT 총괄' }, { role: 'figma_operator', label: 'Figma 담당자' },
].map(item => ({ id: `p2_${company}_${item.role}`, label: `${company.toUpperCase()}사 · ${item.label}` })))
const isDemo = (id: string) => demoAccounts.some(x => x.id === id)

// 관리 대상 SaaS 띠. 로고 파일(public/logos/<slug>.svg, 없으면 .png)이 있으면 로고를, 둘 다 없으면 이름을 보여 준다.
// 로고는 각 사 공식 브랜드 키트 파일만 넣는다(직접 그리거나 변형하지 않는다). 안내: public/logos/README.md
const SAAS = [
  { slug: 'snowflake', name: 'Snowflake' }, { slug: 'databricks', name: 'Databricks' }, { slug: 'salesforce', name: 'Salesforce' },
  { slug: 'datadog', name: 'Datadog' }, { slug: 'tableau', name: 'Tableau Cloud' }, { slug: 'figma', name: 'Figma' },
  { slug: 'github', name: 'GitHub' }, { slug: 'github-copilot', name: 'GitHub Copilot' }, { slug: 'jira', name: 'Jira' },
  { slug: 'slack', name: 'Slack' }, { slug: 'notion', name: 'Notion' },
]
const rows = [SAAS.slice(0, 6), SAAS.slice(6)]
const EXTS = ['svg', 'png'] as const
const logoTry = reactive<Record<string, number>>({}) // 몇 번째 확장자를 시도 중인지
const logoOk = reactive<Record<string, boolean>>({})
const logoSrc = (slug: string) => `${import.meta.env.BASE_URL}logos/${slug}.${EXTS[logoTry[slug] ?? 0]}`
const logoFailed = (slug: string) => (logoTry[slug] ?? 0) >= EXTS.length
function onLogoError(slug: string) { if (!logoOk[slug]) logoTry[slug] = (logoTry[slug] ?? 0) + 1 }

const loginId = ref<string>(accounts[0].loginId)
const password = ref('')
const error = ref('')
const busy = ref(false)
const picked = computed(() => accounts.find(a => a.loginId === loginId.value.trim()) ?? null)

const nextPath = (fallback: string) =>
  typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : fallback

/** 시연 계정은 고르면 바로 로그인한다. */
async function quickLogin(id: string) {
  if (busy.value || !isDemo(id)) return
  loginId.value = id
  password.value = ''
  error.value = ''
  busy.value = true
  try {
    const user = await demoLogin(id)
    await router.replace(nextPath(homeOf(user)))
  } catch (e) {
    error.value = e instanceof Error ? e.message : '시연 로그인에 실패했어요'
  } finally {
    busy.value = false
  }
}

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!password.value && isDemo(loginId.value.trim())) return quickLogin(loginId.value.trim())
  if (!loginId.value.trim() || !password.value) {
    error.value = '아이디와 비밀번호를 입력해 주세요'
    return
  }
  busy.value = true
  try {
    const user = await login(loginId.value.trim(), password.value)
    password.value = ''
    await router.replace(nextPath(homeOf(user)))
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 401
      ? '아이디 또는 비밀번호가 맞지 않아요'
      : (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="uo lg">
    <section class="lg-left" aria-label="UnlockOps 소개">
      <div class="lg-glow" aria-hidden="true" />
      <div class="lg-hero">
        <div class="lg-ring" aria-hidden="true" />
        <div class="lg-shine" aria-hidden="true" />
        <div class="lg-hero-in">
          <svg width="120" height="120" viewBox="0 0 32 32" role="img" aria-label="UnlockOps 심볼: 고리가 열린 자물쇠">
            <rect width="32" height="32" rx="9" fill="#fff" />
            <path d="M11 14V11a5 5 0 0 1 9.6-2" fill="none" stroke="#3B4BD8" stroke-width="2.4" stroke-linecap="round" />
            <rect x="8.5" y="14" width="15" height="11" rx="3" fill="#3B4BD8" />
            <circle cx="16" cy="19.5" r="1.8" fill="#fff" />
          </svg>
          <div>
            <p class="lg-brand">UnlockOps</p>
            <p class="lg-brand-sub">SaaS 권한 승인 · 회수 Agent</p>
          </div>
          <p class="lg-tagline">줄 때는 근거와 비용을 보고,<br>안 쓰면 거둘 후보로 알려 드려요</p>
        </div>

        <div class="lg-saas">
          <p class="lg-saas-k">권한과 비용을 함께 관리하는 SaaS <b>{{ SAAS.length }}</b></p>
          <p class="sr-only">{{ SAAS.map(x => x.name).join(', ') }}</p>
          <div v-for="(row, ri) in rows" :key="ri" class="lg-mq" :class="{ rev: ri === 1 }" aria-hidden="true">
            <div class="lg-mq-track">
              <!-- 끊김 없이 이어지도록 같은 목록을 두 번 둔다. -->
              <template v-for="copy in 2" :key="copy">
                <span v-for="x in row" :key="copy + x.slug" class="lg-logo" :class="`l-${x.slug}`">
                  <img v-if="!logoFailed(x.slug)" v-show="logoOk[x.slug]" :src="logoSrc(x.slug)" alt="" @load="logoOk[x.slug] = true" @error="onLogoError(x.slug)">
                  <span v-if="!logoOk[x.slug]" class="lg-word">{{ x.name }}</span>
                </span>
              </template>
            </div>
          </div>
        </div>
      </div>
    </section>

    <main class="lg-right">
      <form class="lg-form" novalidate @submit.prevent="submit">
        <div>
          <h1>로그인</h1>
          <p class="lg-sub">역할은 계정에 따라 자동으로 정해져요</p>
        </div>

        <fieldset class="lg-accounts">
          <legend>역할을 고르면 바로 로그인</legend>
          <button
            v-for="a in accounts" :key="a.key" type="button" class="lg-account" :class="a.tone"
            :aria-pressed="picked?.key === a.key" :disabled="busy" @click="quickLogin(a.loginId)"
          >
            <span class="lg-avatar" aria-hidden="true">{{ a.initial }}</span>
            <span class="lg-who"><strong>{{ a.title }}</strong><span>{{ a.desc }}</span></span>
            <span class="lg-tag">{{ a.tag }}</span>
          </button>
        </fieldset>

        <label class="lg-field">
          <span>다른 회사 · 담당 역할</span>
          <select :value="isDemo(loginId) && !picked ? loginId : ''" :disabled="busy" @change="quickLogin(($event.target as HTMLSelectElement).value)">
            <option value="" disabled>회사와 역할 선택</option>
            <option v-for="d in demoAccounts" :key="d.id" :value="d.id">{{ d.label }}</option>
          </select>
        </label>
        <label class="lg-field">
          <span>아이디</span>
          <input v-model="loginId" type="text" autocomplete="username" :disabled="busy" placeholder="예: p2_a_requester" :aria-invalid="!!error">
        </label>
        <label class="lg-field">
          <span>비밀번호 (직접 로그인할 때만)</span>
          <input v-model="password" type="password" autocomplete="current-password" :disabled="busy" placeholder="시연 계정은 비워 두세요" :aria-invalid="!!error">
        </label>

        <p v-if="error" class="lg-err" role="alert">{{ error }}</p>

        <button type="submit" class="lg-cta" :disabled="busy">{{ busy ? '확인 중…' : (picked?.cta ?? '로그인') }}</button>
        <p class="lg-fine">시연 환경입니다. 실제 회사 계정과 연결되어 있지 않아요.</p>
      </form>
    </main>
  </div>
</template>

<style scoped>
.lg { display: flex; flex-wrap: wrap; }
.lg-left { flex: 1 1 480px; min-width: 0; position: relative; overflow: hidden; padding: 48px 56px; box-sizing: border-box; display: flex; }
.lg-glow { position: absolute; top: -160px; left: -120px; width: 760px; height: 640px; border-radius: 50%; background: radial-gradient(closest-side at 55% 50%, rgba(122,92,240,0.30), rgba(59,75,216,0.16) 50%, rgba(246,247,252,0) 100%); pointer-events: none; }
.lg-hero { position: relative; overflow: hidden; flex: 1; min-height: min(838px, calc(100vh - 96px)); border-radius: 28px; padding: 56px 0 44px; box-sizing: border-box; background: var(--uo-hero); color: #fff; display: flex; flex-direction: column; justify-content: space-between; gap: 48px; }
.lg-ring { position: absolute; right: -120px; top: -80px; width: 460px; height: 460px; border-radius: 50%; border: 48px solid rgba(255,255,255,0.14); box-sizing: border-box; }
.lg-shine { position: absolute; right: 40px; bottom: -140px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(closest-side, rgba(255,255,255,0.28), rgba(255,255,255,0)); }
.lg-hero-in { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 28px; padding: 0 64px; margin: auto 0; }
/* SaaS 띠: 양 끝은 흐리게, 두 줄은 반대 방향. 마우스를 올리면 멈추고, 동작 줄이기 설정이면 움직이지 않는다. */
.lg-saas { position: relative; display: flex; flex-direction: column; gap: 14px; }
.lg-saas-k { margin: 0 64px 4px; font-size: 13px; font-weight: 600; color: rgba(255,255,255,.72); }
.lg-saas-k b { margin-left: 4px; font-family: var(--uo-font-en); color: #fff; }
.lg-mq { overflow: hidden; -webkit-mask-image: linear-gradient(90deg, transparent, #000 12%, #000 88%, transparent); mask-image: linear-gradient(90deg, transparent, #000 12%, #000 88%, transparent); }
.lg-mq-track { display: flex; width: max-content; animation: lg-mq 38s linear infinite; }
.lg-mq.rev .lg-mq-track { animation-direction: reverse; animation-duration: 44s; }
.lg-saas:hover .lg-mq-track { animation-play-state: paused; }
@keyframes lg-mq { to { transform: translateX(-50%); } }
.lg-logo { flex: 0 0 auto; height: 52px; padding: 0 22px; margin-right: 12px; display: inline-flex; align-items: center; border-radius: 14px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); }
/* 구름처럼 세로로 긴 로고는 같은 높이면 작아 보여서 조금 키운다. */
.lg-logo.l-salesforce img { height: 36px; }
/* 가로 비율은 원본 그대로(max-width를 두면 긴 로고가 가로로 눌린다). 색은 파일에서 이미 흰색으로 맞춘다(Figma 심볼만 원래 색 유지). */
.lg-logo img { height: 26px; width: auto; opacity: .92; }
.lg-word { font-family: var(--uo-font-en); font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: rgba(255,255,255,.88); white-space: nowrap; }
@media (prefers-reduced-motion: reduce) {
  .lg-mq { -webkit-mask-image: none; mask-image: none; }
  .lg-mq-track { animation: none; width: auto; flex-wrap: wrap; row-gap: 10px; padding: 0 64px; }
  .lg-mq-track > .lg-logo:nth-child(n + 7) { display: none; }
}
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.lg-brand { margin: 0; font-family: var(--uo-font-en); font-size: 72px; font-weight: 700; letter-spacing: -0.04em; line-height: 1; }
.lg-brand-sub { margin: 14px 0 0; font-size: 22px; font-weight: 500; color: #EDEBFF; }
.lg-tagline { margin: 0; font-size: 20px; line-height: 1.6; max-width: 420px; }
.lg-right { flex: 1 1 440px; min-width: 0; display: flex; align-items: center; justify-content: center; padding: 48px 24px; box-sizing: border-box; }
.lg-form { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 20px; }
.lg-form h1 { margin: 0; font-size: 32px; font-weight: 700; letter-spacing: -0.01em; }
.lg-sub { margin: 8px 0 0; font-size: 15px; color: var(--uo-muted); }
.lg-accounts { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.lg-accounts legend { font-size: 13px; font-weight: 600; color: var(--uo-ink-2); margin-bottom: 10px; }
.lg-account { display: flex; align-items: center; gap: 14px; min-height: 64px; padding: 14px 16px; text-align: left; font: inherit; color: var(--uo-ink); background: #fff; border: 2px solid var(--uo-line); border-radius: 14px; cursor: pointer; }
.lg-account[aria-pressed="true"] { background: #F5F6FF; border-color: var(--uo-primary); }
.lg-account.t-blue { --avbg: #DDE2FF; --avfg: #3B4BD8; --tagbg: #EEF0FF; --tagfg: #2F3DB8; }
.lg-account.t-violet { --avbg: #EAE3FF; --avfg: #6A45E0; --tagbg: #F1ECFF; --tagfg: #5B3FD6; }
.lg-account.t-indigo { --avbg: #E1E4F5; --avfg: #2B3480; --tagbg: #ECEEF8; --tagfg: #2B3480; }
.lg-avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: var(--avbg); color: var(--avfg); display: flex; align-items: center; justify-content: center; font-weight: 700; }
.lg-who { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.lg-who strong { font-size: 15px; font-weight: 600; }
.lg-who span { font-size: 13px; color: var(--uo-muted); }
.lg-tag { font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px; background: var(--tagbg); color: var(--tagfg); }
.lg-field { display: flex; flex-direction: column; gap: 6px; margin: 0; font-size: 13px; font-weight: 600; color: var(--uo-ink-2); }
.lg-field input, .lg-field select { height: 48px; padding: 0 14px; border: 1px solid var(--uo-line-strong); border-radius: 12px; font: inherit; font-size: 15px; font-weight: 400; color: var(--uo-ink); background: #fff; box-sizing: border-box; }
.lg-err { margin: 0; font-size: 14px; font-weight: 600; color: var(--uo-bad); }
.lg-cta { height: 52px; border: 0; border-radius: 12px; background: var(--uo-gradient); color: #fff; font: inherit; font-size: 16px; font-weight: 600; cursor: pointer; }
.lg-cta:disabled { opacity: .6; cursor: progress; }
.lg-fine { margin: 0; font-size: 12px; line-height: 1.6; color: var(--uo-muted); }
@media (max-width: 900px) {
  .lg-left { padding: 16px 16px 0; }
  .lg-hero { min-height: auto; padding: 36px 0 28px; }
  .lg-hero-in { padding: 0 28px; }
  .lg-saas-k { margin: 0 28px 2px; }
  .lg-logo { height: 44px; padding: 0 16px; }
  .lg-word { font-size: 15px; }
  .lg-hero svg { width: 72px; height: 72px; }
  .lg-brand { font-size: 44px; }
}
</style>
