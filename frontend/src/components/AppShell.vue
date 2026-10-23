<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import lockImg from '../assets/lock.jpg'
import { currentUser, homeOf, logout } from '../session'
import { personaAvatar } from '../lib/persona'

export interface HelpContent { howto: { t: string; d: string }[]; faqs: { q: string; a: string }[] }

const props = defineProps<{ help: HelpContent; showLock?: boolean }>()

const route = useRoute()
const router = useRouter()
const helpOpen = ref(false)
const error = ref('')

// 왼쪽 메뉴는 역할마다 다르다. 메뉴를 숨겨도 실제 차단은 서버가 한다.
// 회수 점검은 v2 서버가 알려 주는 can_reclaim(권한 담당자)일 때만. v1(구 계정)은 목업 화면이라 승인자 모두에게 보인다.
const nav = computed(() => currentUser.value?.role === 'APPROVER'
  ? [
      { to: '/approvals', label: '승인함', icon: 'M4 13l3-8h10l3 8v6H4zM4 13h5l1 2h4l1-2h5' },
      ...(currentUser.value.workflow_version === 1 || currentUser.value.can_reclaim
        ? [{ to: '/revocations', label: '회수 점검', icon: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 8v4l3 2' }] : []),
    ]
  : [
      { to: '/', label: '홈', icon: 'M3 11l9-7 9 7M5 10v10h14V10' },
      { to: '/requests', label: '내 요청', icon: 'M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM8 8h8M8 12h8M8 16h5' },
    ])
const avatar = computed(() => currentUser.value ? personaAvatar(currentUser.value) : null)
const home = computed(() => currentUser.value ? homeOf(currentUser.value) : '/')

function openHelp() { helpOpen.value = true }
defineExpose({ openHelp })

async function signOut() {
  error.value = ''
  try { await logout(); await router.replace('/login') } catch { error.value = '로그아웃하지 못했어요. 잠시 뒤 다시 시도해 주세요.' }
}
</script>

<template>
  <div class="uo sh">
    <nav class="sh-nav" aria-label="주 메뉴">
      <RouterLink :to="home" class="sh-logo" aria-label="UnlockOps 홈">
        <svg width="36" height="36" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="sh-lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3B4BD8" /><stop offset="1" stop-color="#7A5CF0" /></linearGradient></defs><rect width="32" height="32" rx="9" fill="url(#sh-lg)" /><path d="M11 14V11a5 5 0 0 1 9.6-2" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" /><rect x="8.5" y="14" width="15" height="11" rx="3" fill="#fff" /><circle cx="16" cy="19.5" r="1.8" fill="#3B4BD8" /></svg>
      </RouterLink>
      <RouterLink
        v-for="n in nav" :key="n.label" :to="n.to" class="sh-nav-link" :aria-label="n.label"
        :aria-current="typeof n.to === 'string' && route.path === n.to && !route.hash ? 'page' : undefined"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="n.icon" /></svg>
      </RouterLink>
    </nav>

    <main class="sh-main">
      <div class="sh-glow" aria-hidden="true" />
      <div class="sh-inner">
        <!-- 자물쇠는 화면 전체가 아니라 본문 폭(최대 1180px) 안에서 오른쪽에 붙인다. 넓은 화면에서 로그아웃 버튼 바깥으로 나가지 않게. -->
        <img v-if="props.showLock" class="sh-lock" :src="lockImg" alt="" aria-hidden="true">
        <header class="sh-head">
          <div class="sh-brand">UnlockOps <span>SaaS 권한 승인 · 회수 Agent</span></div>
          <div class="sh-me">
            <button type="button" class="sh-pill" @click="openHelp">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.7c0 1.7-2.4 2.1-2.4 3.6M12 17h.01" /></svg>도움말
            </button>
            <span v-if="currentUser" class="sh-who">{{ currentUser.name }} · {{ currentUser.department }}<template v-if="currentUser.role === 'APPROVER'"> (승인자)</template></span>
            <span v-if="avatar" class="sh-avatar" aria-hidden="true" :style="{ background: avatar.bg, color: avatar.fg, borderColor: avatar.fg }">{{ avatar.initial }}</span>
            <button type="button" class="sh-pill" @click="signOut">로그아웃</button>
          </div>
        </header>
        <p v-if="error" class="sh-err" role="alert">{{ error }}</p>
        <slot />
      </div>
    </main>

    <div v-if="helpOpen" class="sh-help">
      <button type="button" class="sh-scrim" aria-label="도움말 닫기" @click="helpOpen = false" />
      <aside class="sh-drawer" role="dialog" aria-modal="true" aria-labelledby="sh-help-t">
        <div class="sh-drawer-head">
          <h2 id="sh-help-t">도움말</h2>
          <button type="button" class="sh-x" aria-label="닫기" @click="helpOpen = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <h3>이렇게 쓰세요</h3>
        <ol class="sh-howto">
          <li v-for="(h, i) in help.howto" :key="h.t"><span aria-hidden="true">{{ i + 1 }}</span><span><strong>{{ h.t }}</strong><span>{{ h.d }}</span></span></li>
        </ol>
        <h3>자주 묻는 질문</h3>
        <details v-for="f in help.faqs" :key="f.q" class="sh-faq"><summary>{{ f.q }}</summary><p>{{ f.a }}</p></details>
        <slot name="help-extra" />
      </aside>
    </div>
  </div>
</template>

<style scoped>
.sh { display: flex; }
.sh-nav { flex: 0 0 72px; position: sticky; top: 0; align-self: flex-start; height: 100vh; display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 20px 0; background: rgba(255,255,255,0.7); border-right: 1px solid var(--uo-line); box-sizing: border-box; z-index: 2; }
.sh-logo { display: flex; margin-bottom: 20px; }
.sh-nav-link { position: relative; width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: var(--uo-muted); transition: background-color .15s ease, color .15s ease; }
.sh-nav-link[aria-current="page"] { background: #E8EBFF; color: var(--uo-primary); }
.sh-nav-link:hover, .sh-nav-link:focus-visible { background: var(--uo-primary-soft); color: var(--uo-primary); }
.sh-nav-link::after { content: attr(aria-label); position: absolute; left: 54px; top: 50%; transform: translate(-4px, -50%); white-space: nowrap; font-size: 13px; font-weight: 600; color: #fff; background: var(--uo-ink); padding: 6px 10px; border-radius: 8px; opacity: 0; pointer-events: none; transition: opacity .15s ease, transform .15s ease; z-index: 30; }
.sh-nav-link:hover::after, .sh-nav-link:focus-visible::after { opacity: 1; transform: translate(0, -50%); }
/* 배경 장식은 잘라 내되 스크롤 영역은 만들지 않는다(clip). hidden이면 안쪽의 position: sticky가 동작하지 않는다. */
.sh-main { flex: 999 1 560px; min-width: 0; position: relative; overflow: hidden; overflow: clip; }
.sh-glow { position: absolute; top: -220px; right: -160px; width: 820px; height: 720px; border-radius: 50%; background: radial-gradient(closest-side at 55% 50%, rgba(122,92,240,0.38), rgba(59,75,216,0.22) 45%, rgba(246,247,252,0) 100%); filter: blur(10px); pointer-events: none; }
.sh-lock { position: absolute; top: 104px; right: 72px; width: 216px; height: 216px; object-fit: contain; mix-blend-mode: multiply; pointer-events: none; }
.sh-inner { position: relative; max-width: 1180px; margin: 0 auto; padding: 44px 48px 64px; box-sizing: border-box; }
.sh-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.sh-brand { font-family: var(--uo-font-en); font-weight: 700; font-size: 22px; letter-spacing: -0.02em; }
.sh-brand span { font-family: var(--uo-font); font-weight: 500; font-size: 14px; color: var(--uo-muted); letter-spacing: 0; }
.sh-me { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--uo-muted); flex-wrap: wrap; }
.sh-pill { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border: 1px solid #D5D9EA; border-radius: 999px; background: #fff; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.sh-avatar { width: 36px; height: 36px; box-sizing: border-box; border-radius: 50%; border: 1.5px solid currentColor; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.sh-err { color: var(--uo-bad); font-weight: 600; }
.sh-help { position: fixed; inset: 0; z-index: 50; display: flex; justify-content: flex-end; }
.sh-scrim { position: absolute; inset: 0; border: 0; padding: 0; background: rgba(20,26,51,0.32); cursor: pointer; }
.sh-drawer { position: relative; width: 440px; max-width: 100%; height: 100%; overflow-y: auto; background: #fff; box-shadow: -12px 0 40px rgba(20,26,51,0.18); padding: 28px 28px 40px; box-sizing: border-box; }
.sh-drawer-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.sh-drawer-head h2 { margin: 0; font-size: 22px; font-weight: 700; }
.sh-x { width: 40px; height: 40px; border-radius: 12px; border: 1px solid var(--uo-line); background: #fff; color: var(--uo-ink-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.sh-drawer h3 { margin: 0 0 12px; font-size: 16px; font-weight: 700; }
.sh-howto { list-style: none; margin: 0 0 28px; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.sh-howto li { display: flex; gap: 12px; align-items: flex-start; }
.sh-howto li > span:first-child { width: 24px; height: 24px; flex: 0 0 24px; border-radius: 50%; background: var(--uo-primary); color: #fff; font-family: var(--uo-font-en); font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.sh-howto strong { display: block; font-size: 15px; }
.sh-howto li > span:last-child > span { font-size: 14px; line-height: 1.6; color: var(--uo-muted); }
.sh-faq { border-bottom: 1px solid #EEF0F6; padding: 14px 0; }
.sh-faq summary { font-size: 15px; font-weight: 600; cursor: pointer; }
.sh-faq p { margin: 8px 0 0; font-size: 14px; line-height: 1.65; color: var(--uo-ink-2); }
@media (max-width: 1100px) { .sh-lock { width: 180px; height: 180px; top: 120px; right: 48px; opacity: .35; } }
@media (max-width: 720px) {
  .sh { flex-direction: column; }
  .sh-nav { position: static; height: auto; width: 100%; flex-direction: row; justify-content: flex-start; padding: 10px 16px; border-right: 0; border-bottom: 1px solid var(--uo-line); }
  .sh-logo { margin: 0 12px 0 0; }
  .sh-nav-link::after { display: none; }
  .sh-inner { padding: 20px 16px 48px; }
  .sh-who { display: none; }
  .sh-lock { display: none; }
  /* 휴대폰: 상단 바 한 줄 = 왼쪽 로고 · 메뉴, 오른쪽 도움말 · 로그아웃.
     헤더를 본문에서 꺼내 상단 바 위에 겹쳐 놓는다. 기준을 .sh로 잡으려고 본문 쪽 position을 푼다. */
  .sh { position: relative; overflow-x: clip; }
  .sh-nav { height: 60px; padding: 0 16px; align-items: center; gap: 4px; }
  .sh-nav-link { width: 40px; height: 40px; }
  .sh-main, .sh-inner { position: static; }
  .sh-glow { display: none; }
  .sh-head { position: absolute; top: 0; right: 16px; height: 60px; z-index: 3; }
  .sh-brand, .sh-avatar { display: none; }
  .sh-me { gap: 6px; flex-wrap: nowrap; }
  .sh-pill { height: 34px; padding: 0 12px; font-size: 13px; }
}
@media (max-width: 360px) { .sh-pill svg { display: none; } }
@media (prefers-reduced-motion: reduce) { .sh-nav-link, .sh-nav-link::after { transition: none; } }
</style>
