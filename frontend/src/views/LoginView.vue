<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api'
import { homeOf, login } from '../session'

const router = useRouter()
const route = useRoute()
const loginId = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

// 시연용 계정은 아이디만 채운다. 비밀번호는 .env의 DEMO_PASSWORD를 직접 입력한다.
const demoAccounts = [
  { loginId: 'kim_dev', name: '김개발', desc: '개발팀 사원 · 결제 개편 TF · 권한 요청', tag: '요청자', initial: '김' },
  { loginId: 'park_lead', name: '박리더', desc: '개발팀 차장 · 결제 개편 TF 리더 · 승인·거절', tag: '승인자', initial: '박' },
] as const

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
  <div class="uo login">
    <section class="hero" aria-label="UnlockOps 소개">
      <svg width="96" height="96" viewBox="0 0 32 32" role="img" aria-label="UnlockOps 심볼: 고리가 열린 자물쇠">
        <rect width="32" height="32" rx="9" fill="#fff" />
        <path d="M11 14V11a5 5 0 0 1 9.6-2" fill="none" stroke="#3B4BD8" stroke-width="2.4" stroke-linecap="round" />
        <rect x="8.5" y="14" width="15" height="11" rx="3" fill="#3B4BD8" />
        <circle cx="16" cy="19.5" r="1.8" fill="#fff" />
      </svg>
      <div>
        <p class="uo-logo">UnlockOps</p>
        <p class="uo-logo-sub">권한 진단 Agent</p>
      </div>
      <p class="tagline">막힌 권한, 편리하게<br>근거와 함께 열어드려요</p>
    </section>

    <main class="uo-login-panel">
      <form class="form" novalidate @submit.prevent="submit">
        <div>
          <h1>로그인</h1>
          <p class="uo-sub">역할은 계정에 따라 자동으로 정해져요</p>
        </div>

        <fieldset class="accounts">
          <legend>시연용 계정으로 채우기</legend>
          <button
            v-for="a in demoAccounts" :key="a.loginId" type="button" class="account"
            :aria-pressed="loginId === a.loginId" @click="loginId = a.loginId"
          >
            <span class="avatar" aria-hidden="true">{{ a.initial }}</span>
            <span class="who"><strong>{{ a.name }}</strong><span>{{ a.desc }}</span></span>
            <span class="uo-tag">{{ a.tag }}</span>
          </button>
        </fieldset>

        <label class="field">
          <span>아이디</span>
          <input v-model="loginId" type="text" autocomplete="username" placeholder="예: kim_dev" :aria-invalid="!!error">
        </label>
        <label class="field">
          <span>비밀번호</span>
          <input v-model="password" type="password" autocomplete="current-password" placeholder="비밀번호" :aria-invalid="!!error">
        </label>

        <p v-if="error" class="uo-err" role="alert">{{ error }}</p>

        <button type="submit" class="cta" :disabled="busy">{{ busy ? '확인 중…' : '로그인' }}</button>
        <p class="fine">시연 환경입니다. 실제 회사 계정과 연결되어 있지 않아요.</p>
      </form>
    </main>
  </div>
</template>

<style scoped>
.login { display: flex; flex-wrap: wrap; }
.hero {
  flex: 1 1 480px; min-height: 100vh; box-sizing: border-box; padding: 56px 64px;
  background: var(--uo-hero); color: #fff;
  display: flex; flex-direction: column; justify-content: center; gap: 28px;
}
.uo-logo { margin: 0; font-family: var(--uo-font-en); font-size: 64px; font-weight: 700; letter-spacing: -0.04em; line-height: 1; }
.uo-logo-sub { margin: 14px 0 0; font-size: 20px; font-weight: 500; color: #EDEBFF; }
.tagline { margin: 0; font-size: 20px; line-height: 1.6; }
.uo-login-panel { flex: 1 1 440px; display: flex; align-items: center; justify-content: center; padding: 48px 24px; box-sizing: border-box; }
.form { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 20px; }
h1 { margin: 0; font-size: 32px; font-weight: 700; }
.uo-sub { margin: 8px 0 0; font-size: 15px; color: var(--uo-muted); }
.accounts { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.accounts legend { font-size: 13px; font-weight: 600; color: var(--uo-ink-2); margin-bottom: 10px; }
.account {
  display: flex; align-items: center; gap: 14px; min-height: 64px; padding: 14px 16px; text-align: left;
  background: var(--uo-surface); border: 2px solid var(--uo-line); border-radius: 14px; color: var(--uo-ink); font: inherit; cursor: pointer;
}
.account[aria-pressed="true"] { border-color: var(--uo-primary); background: var(--uo-primary-soft); }
.avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: #DDE2FF; color: var(--uo-primary); display: flex; align-items: center; justify-content: center; font-weight: 700; }
.who { flex: 1; display: flex; flex-direction: column; gap: 2px; font-size: 15px; }
.who span { font-size: 13px; color: var(--uo-muted); }
.uo-tag { font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px; background: var(--uo-primary-soft); color: var(--uo-primary-ink); }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 600; color: var(--uo-ink-2); margin: 0; }
.field input { height: 48px; padding: 0 14px; border: 1px solid var(--uo-line-strong); border-radius: var(--uo-radius); font: inherit; font-size: 15px; font-weight: 400; color: var(--uo-ink); background: #fff; }
.uo-err { margin: 0; font-size: 14px; font-weight: 600; color: var(--uo-bad); }
.cta { height: 52px; border: 0; border-radius: var(--uo-radius); background: var(--uo-gradient); color: #fff; font: inherit; font-size: 16px; font-weight: 600; cursor: pointer; }
.cta:disabled { opacity: .6; cursor: progress; }
.fine { margin: 0; font-size: 12px; line-height: 1.6; color: var(--uo-muted); }
@media (max-width: 900px) {
  .hero { min-height: auto; padding: 40px 24px; }
  .uo-logo { font-size: 44px; }
}
</style>
