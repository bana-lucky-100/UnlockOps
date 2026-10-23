<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { saasBadge } from '../lib/saasBadge'
import { platformOf } from '../lib/platforms'

/**
 * SaaS 심볼. public/logos/mark/<slug>.png(각 사 공식 심볼, 배경만 투명하게 정리)를 쓰고,
 * 파일이 없거나 못 불러오면 이니셜 배지로 대신한다. 로고는 직접 그리거나 색 · 모양을 바꾸지 않는다.
 * platform(서버 코드) 또는 name(화면 이름) 중 하나로 찾는다.
 */
const props = withDefaults(defineProps<{ platform?: string | null; name?: string | null; size?: number; tile?: boolean }>(), { size: 18, tile: false })

const SLUG: Record<string, string> = {
  SNOWFLAKE: 'snowflake', DATABRICKS: 'databricks', SALESFORCE: 'salesforce', DATADOG: 'datadog',
  TABLEAU_CLOUD: 'tableau', TABLEAU: 'tableau', FIGMA: 'figma', GITHUB: 'github', GITHUB_COPILOT: 'github-copilot',
  JIRA: 'jira', SLACK: 'slack', NOTION: 'notion',
  'Snowflake': 'snowflake', 'Databricks': 'databricks', 'Salesforce': 'salesforce', 'Datadog': 'datadog',
  'Tableau Cloud': 'tableau', 'Figma': 'figma', 'GitHub': 'github', 'GitHub Copilot': 'github-copilot',
  'Jira': 'jira', 'Slack': 'slack', 'Notion': 'notion',
}
const label = computed(() => props.name ?? platformOf(props.platform).label)
const slug = computed(() => SLUG[props.platform ?? ''] ?? SLUG[label.value] ?? null)
const failed = ref(false)
watch(slug, () => { failed.value = false })
const badge = computed(() => saasBadge(label.value))
const src = computed(() => `${import.meta.env.BASE_URL}logos/mark/${slug.value}.png`)
</script>

<template>
  <span class="sm" :class="{ tile }" :style="{ width: `${size}px`, height: `${size}px`, ...(!slug || failed ? { background: badge.bg, color: badge.fg } : {}) }" aria-hidden="true">
    <img v-if="slug && !failed" :src="src" alt="" @error="failed = true">
    <span v-else class="sm-mono" :style="{ fontSize: `${Math.max(9, Math.round(size * 0.38))}px` }">{{ badge.mono }}</span>
  </span>
</template>

<style scoped>
.sm { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; border-radius: 4px; box-sizing: border-box; vertical-align: middle; }
.sm.tile { border-radius: 9px; background: #fff; border: 1px solid var(--uo-line, #E4E7F2); padding: 5px; }
.sm img { width: 100%; height: 100%; object-fit: contain; display: block; }
.sm-mono { font-family: var(--uo-font-en); font-weight: 700; line-height: 1; }
</style>
