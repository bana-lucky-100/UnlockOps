<script setup lang="ts">
import AppShell from '../components/AppShell.vue'
import { currentUser } from '../session'

// 4단계(#6)에서 대기 목록 · 내 승인 현황 · 여러 건 승인을 채운다.
const help = {
  // 회사마다 조직 구조(TF · 부서)와 권한 이름이 달라서, 특정 조직에만 맞는 문구는 쓰지 않는다.
  howto: [
    { t: '누가 무엇을 요청했는지 보세요', d: '요청자, 플랫폼, 요청 권한이 승인 카드에 정리돼 있어요' },
    { t: 'AI가 찾은 원인과 근거를 확인하세요', d: '사내 규정에 맞는 최소 권한만 올라와요. 관리자 권한은 자동으로 올라오지 않아요' },
    { t: '거절할 땐 사유를 남겨 주세요', d: '요청자에게 그대로 보여서, 무엇을 바꿔 다시 요청할지 알 수 있어요' },
  ],
  faqs: [],
}
</script>

<template>
  <AppShell :help="help">
    <section class="ah-hero">
      <p class="ah-hello">안녕하세요, {{ currentUser?.name }}님</p>
      <h1 class="ah-title">승인함</h1>
    </section>
  </AppShell>
</template>

<style scoped>
.ah-hero { padding: 72px 0 40px; }
.ah-hello { margin: 0 0 12px; font-family: var(--uo-font-en); font-size: 44px; font-weight: 700; color: var(--uo-primary); }
.ah-title { margin: 0; font-size: 34px; font-weight: 600; }
</style>
