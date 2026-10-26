<!-- 미연결: #29 Phase 2 테스트용 화면 · 기존 화면으로 합쳐지면서 현재 라우터에서 빠져 있어 앱에 연결된 화면에서는 쓰이지 않음(이 Phase 2 파일들끼리만 서로 참조). 되살릴 때는 src/router.ts 주석 참고. -->
<script setup lang="ts">
import AppShell from '../AppShell.vue'
import { currentUser } from '../../session'
import { help } from '../../phase2/presentation'
import '../../phase2/style.css'
</script>
<template>
  <AppShell :help="help">
    <div class="p2">
      <nav class="p2-tabs" aria-label="업무 메뉴">
        <RouterLink to="/access">권한 요청·승인</RouterLink>
        <RouterLink to="/access/new">새 요청</RouterLink>
        <RouterLink v-if="currentUser?.can_reclaim" to="/reclaim">회수 점검·알림</RouterLink>
      </nav>
      <p v-if="!currentUser" class="p2-alert" role="alert">
        로그인이 필요합니다. <RouterLink to="/login" class="p2-link">다시 로그인</RouterLink>
      </p>
      <slot />
    </div>
  </AppShell>
</template>
