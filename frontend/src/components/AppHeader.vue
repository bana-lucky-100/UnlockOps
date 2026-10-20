<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { currentUser, logout } from '../session'

const router = useRouter()
const error = ref('')

async function signOut() {
  error.value = ''
  try {
    await logout()
    await router.replace('/login')
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>

<template>
  <header class="bar">
    <div class="uo-logo">UnlockOps <span>권한 진단 Agent</span></div>
    <div v-if="currentUser" class="me">
      <span>{{ currentUser.name }} · {{ currentUser.department }}<template v-if="currentUser.role === 'APPROVER'"> (승인자)</template></span>
      <span class="avatar" aria-hidden="true">{{ currentUser.name.slice(0, 1) }}</span>
      <button type="button" class="out" @click="signOut">로그아웃</button>
    </div>
  </header>
  <p v-if="error" class="uo-err" role="alert">{{ error }}</p>
</template>

<style scoped>
.bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 20px 0; }
.uo-logo { font-family: var(--uo-font-en); font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
.uo-logo span { font-family: var(--uo-font); font-size: 14px; font-weight: 500; color: var(--uo-muted); letter-spacing: 0; }
.me { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--uo-muted); }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: #DDE2FF; color: var(--uo-primary); display: flex; align-items: center; justify-content: center; font-weight: 600; }
.out { height: 36px; padding: 0 14px; border: 1px solid #D5D9EA; border-radius: 999px; background: #fff; color: var(--uo-ink-2); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.uo-err { margin: 0 0 12px; color: var(--uo-bad); font-weight: 600; }
</style>
