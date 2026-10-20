<script setup lang="ts">
import { ref } from 'vue'
import AppShell, { type AgentItem } from '../components/AppShell.vue'
import { currentUser } from '../session'

// 4단계(#6)에서 대기 목록 · 내 승인 현황 · 여러 건 승인을 채운다.
const shell = ref<InstanceType<typeof AppShell>>()
const agentItems: AgentItem[] = [
  { label: '승인 기준 · 거절 사유', sub: '무엇을 보고 결정하나요', icon: 'M9.5 9.5a2.5 2.5 0 0 1 4.9.7c0 1.7-2.4 2.1-2.4 3.6M12 17h.01', action: () => shell.value?.openHelp() },
]
const help = {
  howto: [
    { t: '우리 구성원인가요?', d: 'TF 자원은 TF 구성원, 그 외는 내 부서 구성원의 요청이 나에게 와요' },
    { t: '권한이 꼭 필요한 만큼인가요?', d: 'AI는 Write · Developer · 채널 참여 · 읽기처럼 최소 권한만 제안해요. Admin은 올라오지 않아요' },
    { t: '거절할 땐 사유를 남겨 주세요', d: '요청자에게 그대로 보여서, 무엇을 바꿔 다시 요청할지 알 수 있어요' },
  ],
  faqs: [],
}
</script>

<template>
  <AppShell ref="shell" :agent-items="agentItems" :help="help">
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
