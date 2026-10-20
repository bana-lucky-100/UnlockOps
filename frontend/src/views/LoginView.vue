<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api'
import { homeOf, login } from '../session'

const router = useRouter()
const route = useRoute()

// 시연 계정. 비밀번호는 .env.example의 시연 기본값과 같다(실제 회사 계정과 연결되지 않은 시연 환경 전용).
const DEMO_PASSWORD = 'demo1234'
const accounts = [
  { key: 'EMPLOYEE', loginId: 'kim_dev', title: '직원 · 김개발', desc: '개발팀 사원 · 결제 개편 TF · 권한 요청', initial: '김', tag: '직원', tone: 'blue', cta: '직원으로 로그인' },
  { key: 'APPROVER', loginId: 'park_lead', title: '승인자 · 박리더', desc: '개발팀 차장 · 결제 개편 TF 리더 · 승인·거절', initial: '박', tag: '승인자', tone: 'green', cta: '승인자로 로그인' },
] as const

const loginId = ref<string>(accounts[0].loginId)
const password = ref(DEMO_PASSWORD)
const error = ref('')
const busy = ref(false)
const picked = computed(() => accounts.find(a => a.loginId === loginId.value.trim()) ?? null)

function pick(a: typeof accounts[number]) {
  loginId.value = a.loginId
  password.value = DEMO_PASSWORD
  error.value = ''
}

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!loginId.value.trim() || !password.value) {
    error.value = '아이디와 비밀번호를 입력해 주세요'
    return
  }
  busy.value = true
  try {
    const user = await login(loginId.value.trim(), password.value)
    password.value = ''
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : homeOf(user)
    await router.replace(next)
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
            <p class="lg-brand-sub">권한 진단 Agent</p>
          </div>
          <p class="lg-tagline">막힌 권한, 편리하게<br>근거와 함께 열어드려요</p>
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
          <legend>시연용 계정으로 채우기</legend>
          <button
            v-for="a in accounts" :key="a.key" type="button" class="lg-account" :class="a.tone"
            :aria-pressed="picked?.key === a.key" @click="pick(a)"
          >
            <span class="lg-avatar" aria-hidden="true">{{ a.initial }}</span>
            <span class="lg-who"><strong>{{ a.title }}</strong><span>{{ a.desc }}</span></span>
            <span class="lg-tag">{{ a.tag }}</span>
          </button>
        </fieldset>

        <label class="lg-field">
          <span>아이디</span>
          <input v-model="loginId" type="text" autocomplete="username" placeholder="예: kim_dev" :aria-invalid="!!error">
        </label>
        <label class="lg-field">
          <span>비밀번호</span>
          <input v-model="password" type="password" autocomplete="current-password" placeholder="비밀번호" :aria-invalid="!!error">
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
.lg-hero { position: relative; overflow: hidden; flex: 1; min-height: min(838px, calc(100vh - 96px)); border-radius: 28px; padding: 56px 64px; box-sizing: border-box; background: var(--uo-hero); color: #fff; display: flex; flex-direction: column; justify-content: center; }
.lg-ring { position: absolute; right: -120px; top: -80px; width: 460px; height: 460px; border-radius: 50%; border: 48px solid rgba(255,255,255,0.14); box-sizing: border-box; }
.lg-shine { position: absolute; right: 40px; bottom: -140px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(closest-side, rgba(255,255,255,0.28), rgba(255,255,255,0)); }
.lg-hero-in { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 28px; }
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
.lg-account.blue { --avbg: #DDE2FF; --avfg: #3B4BD8; --tagbg: #EEF0FF; --tagfg: #2F3DB8; }
.lg-account.green { --avbg: #E0F0E6; --avfg: #1A7340; --tagbg: #E6F4EC; --tagfg: #1A7340; }
.lg-avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: var(--avbg); color: var(--avfg); display: flex; align-items: center; justify-content: center; font-weight: 700; }
.lg-who { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.lg-who strong { font-size: 15px; font-weight: 600; }
.lg-who span { font-size: 13px; color: var(--uo-muted); }
.lg-tag { font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px; background: var(--tagbg); color: var(--tagfg); }
.lg-field { display: flex; flex-direction: column; gap: 6px; margin: 0; font-size: 13px; font-weight: 600; color: var(--uo-ink-2); }
.lg-field input { height: 48px; padding: 0 14px; border: 1px solid var(--uo-line-strong); border-radius: 12px; font: inherit; font-size: 15px; font-weight: 400; color: var(--uo-ink); background: #fff; box-sizing: border-box; }
.lg-err { margin: 0; font-size: 14px; font-weight: 600; color: var(--uo-bad); }
.lg-cta { height: 52px; border: 0; border-radius: 12px; background: var(--uo-gradient); color: #fff; font: inherit; font-size: 16px; font-weight: 600; cursor: pointer; }
.lg-cta:disabled { opacity: .6; cursor: progress; }
.lg-fine { margin: 0; font-size: 12px; line-height: 1.6; color: var(--uo-muted); }
@media (max-width: 900px) {
  .lg-left { padding: 16px 16px 0; }
  .lg-hero { min-height: auto; padding: 36px 28px; }
  .lg-hero svg { width: 72px; height: 72px; }
  .lg-brand { font-size: 44px; }
}
</style>
