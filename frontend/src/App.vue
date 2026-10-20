<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <!-- 같은 화면 안에서 다른 요청으로 이동해도(예: 같은 시각에 보낸 요청) 새로 불러오도록 경로마다 다시 만든다 -->
  <RouterView :key="$route.path" />
</template>
