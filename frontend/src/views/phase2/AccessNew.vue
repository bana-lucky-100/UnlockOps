<!-- 미연결: #29 Phase 2 테스트용 화면 · 기존 화면으로 합쳐지면서 현재 라우터에서 빠져 있음(어디에서도 불리지 않음). 되살릴 때는 src/router.ts 주석 참고. -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Workspace from '../../components/phase2/Workspace.vue'
import { phase2, errorMessage, type CatalogItem } from '../../phase2/api'
import { platforms } from '../../phase2/presentation'
import type { Platform } from '../../contracts/phase2'
import { currentUser } from '../../session'
const router = useRouter()
const platform = ref<Platform>('GITHUB'),
  entitlement = ref(''),
  contents = ref(''),
  error = ref(''),
  catalogError = ref(''),
  busy = ref(false)
const acceptedId = ref(''),
  catalog = ref<CatalogItem[]>([])
const options = computed(() => catalog.value.filter((x) => x.platform === platform.value))
async function loadCatalog() {
  try {
    catalog.value = await phase2.catalog()
    catalogError.value = ''
  } catch (e) {
    catalogError.value = errorMessage(e)
  }
}
onMounted(loadCatalog)
async function submit() {
  if (busy.value || acceptedId.value) return
  const owner = currentUser.value?.id
  if (!owner) return
  if (!contents.value.trim()) {
    error.value = '업무 목적과 필요한 권한을 입력해 주세요.'
    return
  }
  busy.value = true
  error.value = ''
  const chosen = options.value.find((x) => x.entitlement_id === entitlement.value)
  try {
    const result = await phase2.submit(owner, {
      schema_version: 2,
      platform: platform.value,
      contents: contents.value.trim(),
      ...(chosen ? { resource_id: chosen.resource_id, entitlement_id: chosen.entitlement_id } : {})
    })
    if (currentUser.value?.id !== owner) return
    acceptedId.value = result.problem_id
    await router.push(`/access/${result.problem_id}`)
  } catch (e) {
    if (currentUser.value?.id === owner)
      error.value = acceptedId.value ? '요청은 접수되었습니다. 아래에서 상세를 열어 주세요.' : errorMessage(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <Workspace>
    <header class="p2-heading">
      <h1>새 권한 요청</h1>
      <p class="p2-muted">업무 목적·대상 자원·오류 또는 필요한 권한을 함께 적어 주세요.</p>
    </header>
    <div class="p2-grid">
      <form class="p2-card" @submit.prevent="submit">
        <p v-if="error" class="p2-alert" role="alert">{{ error }}</p>
        <p v-if="acceptedId" class="p2-notice">
          접수되었습니다.
          <RouterLink :to="`/access/${acceptedId}`" class="p2-link">요청 상세 열기 →</RouterLink>
        </p>
        <fieldset :disabled="busy || !!acceptedId" style="border: 0; padding: 0; margin: 0">
          <label
            >플랫폼<select v-model="platform" @change="entitlement = ''">
              <option v-for="(name, code) in platforms" :key="code" :value="code">{{ name }}</option>
            </select></label
          >
          <label
            >대상 자원·권한<select v-model="entitlement">
              <option value="">요청 내용으로 분석</option>
              <option v-for="item in options" :key="item.entitlement_id" :value="item.entitlement_id">
                {{ item.resource_name }} · {{ item.entitlement_code }}
              </option>
            </select></label
          >
          <p v-if="catalogError" class="p2-alert" role="alert">
            {{ catalogError }}
            <button type="button" class="p2-btn" @click="loadCatalog">자원 다시 조회</button>
          </p>
          <label
            >요청 내용<textarea
              v-model="contents"
              required
              maxlength="5000"
              rows="7"
              placeholder="결제 개편 TF에서 개발 업무를 맡았습니다. GitHub Copilot 좌석이 필요합니다. 업무 목적과 사용 기간을 검토해 주세요."
            />
          </label>
          <div class="p2-row">
            <small>{{ contents.length }} / 5,000자</small
            ><button class="p2-btn primary" type="submit">{{ busy ? '접수 중…' : '분석 요청' }}</button>
          </div>
        </fieldset>
      </form>
      <aside class="p2-card">
        <h2>요청 후 진행</h2>
        <ol>
          <li>회사 규정·자격·비용 확인</li>
          <li>지정된 순서대로 승인 검토</li>
          <li>최종 승인 후 권한 반영·확인</li>
        </ol>
        <p class="p2-muted">
          조건이 부족하면 보류 또는 담당자 검토로 안내합니다. 해당 상태에서 재개하면 최신 조건으로 다시
          분석합니다.
        </p>
      </aside>
    </div>
  </Workspace>
</template>
