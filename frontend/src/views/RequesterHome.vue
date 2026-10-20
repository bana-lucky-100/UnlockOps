<script setup lang="ts">
import AppHeader from '../components/AppHeader.vue'
import { currentUser } from '../session'
</script>

<template>
  <div class="uo">
    <div class="page">
      <AppHeader />
      <main>
        <p class="hello">안녕하세요, {{ currentUser?.name }}님</p>
        <h1>어디가 막혔나요?</h1>
        <!-- 2단계(#6): 플랫폼 선택 · 증상 입력 · 내 요청 목록 -->
      </main>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; padding: 0 24px 48px; }
.hello { margin: 48px 0 8px; font-family: var(--uo-font-en); font-size: 40px; font-weight: 700; color: var(--uo-primary); }
h1 { margin: 0; font-size: 30px; font-weight: 600; }
</style>
