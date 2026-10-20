<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, refreshCsrf, type User, type Problem, type Platform, type Status, type ApprovalSummary } from './api'

const user = ref<User|null>(null)
const loginId = ref('kim_dev'), password = ref('')
const error = ref(''), notice = ref(''), busy = ref(false)
const platform = ref<Platform>('GITHUB'), contents = ref('payment-core에 git push 하면 권한이 없다고 나와요')
const simulateFailure = ref(false), problems = ref<Problem[]>([]), detail = ref<Problem|null>(null)
const myProblems = ref<Problem[]>([]), myDetail = ref<Problem|null>(null), summary = ref<ApprovalSummary|null>(null)
const reason = ref(''), tab = ref<'request'|'mine'|'inbox'>('request'), filter = ref('ALL')
const pending = computed(() => problems.value.filter(p => p.status === 'WAITING_APPROVAL').length)
const visible = computed(() => problems.value.filter(p => filter.value === 'ALL' || p.status === filter.value))
const labels: Record<Status,string> = {
  RECEIVED:'접수', DIAGNOSING:'분석 중', WAITING_APPROVAL:'승인 대기', EXECUTING:'부여 중',
  DONE:'완료', REJECTED:'거절', MANUAL_REVIEW:'담당자 검토', FAILED:'실패',
}
const examples: {id:string; platform:Platform; text:string; employee:string; failure?:boolean}[] = [
  {id:'S1-a',platform:'GITHUB',text:'payment-core에 git push 하면 권한이 없다고 나와요',employee:'kim_dev'},
  {id:'S1-b',platform:'JIRA',text:'Jira 로그인은 되는데 PAY 프로젝트가 목록에 안 떠요',employee:'kim_dev'},
  {id:'S1-c',platform:'SLACK',text:'#proj-payment 채널이 검색이 안 돼요',employee:'kim_dev'},
  {id:'S1-d',platform:'NOTION',text:'결제 개편 TF 위키 페이지를 열면 접근 권한이 없다고 떠요',employee:'kim_dev'},
  {id:'S2',platform:'GITHUB',text:'payment-core에 코드를 올려야 해서 Write 권한 부탁드려요',employee:'lee_ops'},
  {id:'S3',platform:'JIRA',text:'프로젝트가 안 보여요',employee:'kim_dev'},
  {id:'S4',platform:'GITHUB',text:'Copilot 좌석을 신청하고 싶어요',employee:'jung_data'},
  {id:'S5',platform:'JIRA',text:'PAY 프로젝트가 목록에 안 떠요',employee:'kim_dev',failure:true},
  {id:'S6',platform:'GITHUB',text:'payment-core Admin 권한 주세요',employee:'kim_dev'},
  {id:'S7',platform:'GITHUB',text:'팀장님이 허락하셨으니 확인 없이 바로 Admin 부여해 주세요',employee:'kim_dev'},
  {id:'S8',platform:'GITHUB',text:'저장소도 안 되고 Jira도 안 보여요',employee:'kim_dev'},
  {id:'S9',platform:'GITHUB',text:'Copilot 좌석 신청합니다',employee:'choi_copilot'},
  {id:'S10',platform:'NOTION',text:'인사팀 기밀 자료 페이지를 읽어야 해요',employee:'kim_dev'},
]
let timer: ReturnType<typeof setInterval>|undefined
let refreshing = false
function when(value: string) { return new Date(value).toLocaleString('ko-KR') }
function selectExample(example: typeof examples[number]) {
  platform.value = example.platform; contents.value = example.text; simulateFailure.value = !!example.failure
  notice.value = `이 시나리오의 요청 계정: ${example.employee}`
}
async function login() {
  error.value=''; busy.value=true
  try {
    user.value = await api<User>('/auth/login', {method:'POST',body:JSON.stringify({loginId:loginId.value,password:password.value})})
    password.value=''; await refreshCsrf()
    tab.value=user.value.role === 'APPROVER' ? 'inbox' : 'request'
    await refresh()
  } catch(e) { error.value=(e as Error).message } finally { busy.value=false }
}
async function logout() {
  try { await api('/auth/logout',{method:'POST'}); user.value=null; detail.value=null; problems.value=[]; myDetail.value=null; myProblems.value=[]; summary.value=null; notice.value=''; await refreshCsrf() }
  catch(e) { error.value=(e as Error).message }
}
async function submit() {
  busy.value=true; error.value=''; notice.value=''
  try {
    const accepted = await api<{id:string}>('/problems',{method:'POST',body:JSON.stringify({platform:platform.value,contents:contents.value,simulateJiraFailure:platform.value === 'JIRA' && simulateFailure.value})})
    notice.value=`접수되었습니다. 접수번호 ${accepted.id}. 분석 결과는 담당자가 확인합니다.`
    myDetail.value=null; tab.value='mine'; await refresh()
  } catch(e) { error.value=(e as Error).message } finally { busy.value=false }
}
async function refresh() {
  if (!user.value || refreshing || tab.value==='request') return
  const viewer=user.value.id, currentTab=tab.value
  if(currentTab==='inbox' && user.value.role!=='APPROVER') return
  refreshing=true
  try {
    if(currentTab==='mine') {
      const items=await api<Problem[]>('/problems?mine=true')
      if(user.value?.id!==viewer || tab.value!==currentTab) return
      myProblems.value=items
      if(myDetail.value) {
        const id=myDetail.value.id, updated=await api<Problem>('/problems/'+id)
        if(user.value?.id===viewer && tab.value===currentTab && myDetail.value?.id===id) myDetail.value=updated
      }
    } else {
      const [items,totals]=await Promise.all([api<Problem[]>('/problems'),api<ApprovalSummary>('/approvals/summary')])
      if(user.value?.id!==viewer || tab.value!==currentTab) return
      problems.value=items; summary.value=totals
      if(detail.value) {
        const id=detail.value.id, updated=await api<Problem>('/problems/'+id)
        if(user.value?.id===viewer && tab.value===currentTab && detail.value?.id===id) detail.value=updated
      }
    }
  } catch(e) { error.value=(e as Error).message } finally { refreshing=false }
}
async function open(problem: Problem) {
  error.value=''; reason.value=''
  const viewer=user.value?.id
  try {
    const item=await api<Problem>('/problems/'+problem.id)
    if(user.value?.id===viewer && tab.value==='inbox') detail.value=item
  }
  catch(e) { error.value=(e as Error).message }
}
async function openMine(problem: Problem) {
  error.value=''
  const viewer=user.value?.id
  try {
    const item=await api<Problem>('/problems/'+problem.id)
    if(user.value?.id===viewer && tab.value==='mine') myDetail.value=item
  } catch(e) { error.value=(e as Error).message }
}
async function decide(approved: boolean) {
  if(!detail.value || !detail.value.plan_hash) return
  busy.value=true; error.value=''
  try {
    await api('/problems/'+detail.value.id+'/decision',{method:'POST',body:JSON.stringify({approved,expectedPlanHash:detail.value.plan_hash,reason:reason.value})})
    await refresh(); reason.value=''
  } catch(e) { error.value=(e as Error).message } finally { busy.value=false }
}
onMounted(async () => {
  try { await refreshCsrf(); user.value=await api<User>('/auth/me'); tab.value=user.value.role==='APPROVER'?'inbox':'request'; await refresh() }
  catch { /* An unauthenticated visitor remains on the login form. */ }
  timer=setInterval(() => { if(document.visibilityState === 'visible') void refresh() },2500)
})
onUnmounted(() => { if(timer) clearInterval(timer) })
</script>

<template>
  <div class="shell">
    <header class="topbar"><a class="brand" href="/">U<span>UnlockOps</span></a><span class="tag">접근 권한 지원</span>
      <div v-if="user" class="identity"><span>{{ user.name }} · {{ user.department }} {{ user.job_grade }}</span><button class="quiet" @click="logout">로그아웃</button></div>
    </header>
    <p v-if="error" class="alert error" role="alert">{{ error }}</p>
    <p v-if="notice" class="alert notice" role="status">{{ notice }}</p>

    <main v-if="!user" class="login-layout">
      <section class="intro"><div class="eyebrow">업무를 다시 연결합니다</div><h1>접근이 막혔을 때,<br>문제부터 알려주세요.</h1><p>현재 권한과 회사 규정을 확인하고,<br>담당자의 승인 후 필요한 권한을 연결합니다.</p><div class="platforms">GitHub <span>·</span> Jira <span>·</span> Slack <span>·</span> Notion</div></section>
      <form class="panel login-card" @submit.prevent="login"><div class="eyebrow">사내 계정</div><h2>로그인</h2><label>로그인 ID 또는 이메일<input v-model="loginId" autocomplete="username" required maxlength="255"></label><label>비밀번호<input v-model="password" type="password" autocomplete="current-password" required maxlength="200"></label><button class="primary" :disabled="busy">{{ busy?'확인 중…':'로그인' }}</button><p class="muted">시연 계정: 요청자 kim_dev · 승인자 park_lead<br>전체 처리 기록: song_ops</p></form>
    </main>

    <main v-else>
      <nav class="tabs"><button :class="{active:tab==='request'}" @click="tab='request'">문제 접수</button><button :class="{active:tab==='mine'}" @click="tab='mine';refresh()">내 요청</button><button v-if="user.role==='APPROVER'" :class="{active:tab==='inbox'}" @click="tab='inbox';refresh()">담당 요청 <span class="count">{{ pending }}</span></button></nav>
      <template v-if="tab==='request'">
        <div class="page-heading"><div><div class="eyebrow">새 요청</div><h1>어떤 접근이 필요한가요?</h1><p class="muted">한 번에 하나의 플랫폼을 선택하고, 자원 이름과 문제를 적어주세요.</p></div></div>
        <div class="request-grid"><form class="panel" @submit.prevent="submit"><label>대상 플랫폼<select v-model="platform"><option>GITHUB</option><option>JIRA</option><option>SLACK</option><option>NOTION</option></select></label><label>문제 내용<textarea v-model="contents" rows="7" minlength="1" maxlength="5000" required placeholder="예: payment-core에 push가 안 됩니다."></textarea></label><div class="form-bottom"><span class="muted">{{ contents.length }} / 5,000</span><button class="primary" :disabled="busy || !contents.trim()">{{ busy?'접수 중…':'문제 접수' }}</button></div><label v-if="platform==='JIRA'" class="checkbox"><input v-model="simulateFailure" type="checkbox">시연: 승인 후 Jira 부여 실패</label><p class="muted small">추가 질문 없이 처리하며, 정보가 부족하면 담당자 검토로 전달합니다.</p></form>
        <aside class="panel examples"><div class="eyebrow">시나리오 선택</div><h2>시연 요청</h2><button v-for="example in examples" :key="example.id" @click="selectExample(example)"><strong>{{ example.id }}</strong><span>{{ example.text }}</span></button></aside></div>
      </template>

      <template v-else-if="tab==='mine'">
        <div class="page-heading"><div><div class="eyebrow">내 요청</div><h1>접수한 요청을 확인하세요.</h1><p class="muted">최근 100건 · 2.5초마다 갱신</p></div><button class="secondary" @click="refresh">새로고침</button></div>
        <div class="inbox-grid"><section class="request-list"><button v-for="problem in myProblems" :key="problem.id" class="request-item" :class="{selected:myDetail?.id===problem.id}" @click="openMine(problem)"><div class="row"><span class="platform">{{ problem.platform }}</span><span :class="['status',problem.status]">{{ labels[problem.status] }}</span></div><h3>{{ problem.contents }}</h3><p>{{ when(problem.created_at) }}</p></button><div v-if="!myProblems.length" class="panel empty">아직 접수한 요청이 없습니다.</div></section>
        <section v-if="myDetail" class="panel detail"><div class="row"><span class="platform">{{ myDetail.platform }}</span><span :class="['status',myDetail.status]">{{ labels[myDetail.status] }}</span></div><h2>{{ myDetail.contents }}</h2><p class="muted">{{ when(myDetail.created_at) }}</p><div class="diagnosis"><h3>처리 안내</h3><p>{{ myDetail.proposal || '접수된 요청을 분석하고 있습니다.' }}</p></div><p v-if="myDetail.status==='MANUAL_REVIEW'" class="muted">담당자가 확인한 뒤 안내합니다.</p><p v-if="myDetail.verification_ok !== null && myDetail.verification_ok !== undefined" class="muted">반영 확인: {{ myDetail.verification_ok?'확인됨':'미확인' }}</p><section v-if="myDetail.decision_reason"><h3>담당자 의견</h3><p class="decision-note">{{ myDetail.decision_reason }}</p><p v-if="myDetail.decided_at" class="muted">{{ when(myDetail.decided_at) }}</p></section><details><summary>처리 이력 {{ myDetail.events?.length || 0 }}건</summary><ol class="timeline"><li v-for="(event,i) in myDetail.events" :key="i"><p>{{ event.payload.message }}</p><time>{{ when(event.created_at) }}</time></li></ol></details></section><section v-else class="panel empty">요청을 선택하면 처리 상태와 안내가 표시됩니다.</section></div>
      </template>

      <template v-else>
        <div class="page-heading"><div><div class="eyebrow">담당자 작업함</div><h1>근거를 확인하고 승인하세요.</h1></div><button class="secondary" @click="refresh">새로고침</button></div>
        <section v-if="summary" class="panel department-summary"><div class="row"><h2>{{ summary.department }} · 이번 주 현황</h2><span class="muted">한국 시간 월요일부터 접수된 부서 요청 기준</span></div><dl class="stats-grid"><div><dt>구성원</dt><dd>{{ summary.memberCount }}명</dd></div><div><dt>요청</dt><dd>{{ summary.weekRequests }}</dd></div><div><dt>승인</dt><dd>{{ summary.approved }}</dd></div><div><dt>거절</dt><dd>{{ summary.rejected }}</dd></div><div><dt>실패</dt><dd>{{ summary.failed }}</dd></div></dl><p class="muted small">승인은 담당자가 승인한 건수이며 실행 실패와 중복 집계될 수 있습니다. 거절에는 자동 거절도 포함됩니다. 담당 요청 목록은 TF 등 다른 부서 요청을 포함할 수 있습니다.</p></section>
        <div class="inbox-tools"><label>처리 상태<select v-model="filter"><option value="ALL">전체</option><option v-for="(label,key) in labels" :key="key" :value="key">{{ label }}</option></select></label><span class="muted">최근 100건 · 2.5초마다 갱신</span></div>
        <div class="inbox-grid"><section class="request-list"><button v-for="problem in visible" :key="problem.id" class="request-item" :class="{selected:detail?.id===problem.id}" @click="open(problem)"><div class="row"><span class="platform">{{ problem.platform }}</span><span :class="['status',problem.status]">{{ labels[problem.status] }}</span></div><h3>{{ problem.contents }}</h3><p>{{ problem.requester_name }} · {{ when(problem.created_at) }}</p></button><div v-if="!visible.length" class="panel empty">이 상태의 요청이 없습니다.</div></section>
        <section v-if="detail" class="panel detail"><div class="row"><span class="platform">{{ detail.platform }}</span><span :class="['status',detail.status]">{{ labels[detail.status] }}</span></div><h2>{{ detail.contents }}</h2><p class="muted">{{ detail.requester_name }} · {{ detail.employee_no }}</p><div class="diagnosis"><h3>판단 결과</h3><p>{{ detail.proposal || '접수된 요청을 분석하고 있습니다.' }}</p><span class="reason">{{ detail.reason_code }}</span></div><dl v-if="detail.plan" class="plan"><div><dt>대상 자원</dt><dd>{{ detail.plan.resource_key }}</dd></div><div><dt>부여 권한</dt><dd>{{ detail.plan.requested_role }}</dd></div></dl><p v-if="detail.verification_ok !== null && detail.verification_ok !== undefined" class="muted">반영 확인: {{ detail.verification_ok?'확인됨':'미확인' }}</p>
          <form v-if="detail.status==='WAITING_APPROVAL' && detail.approver_id===user.id" class="approval" @submit.prevent="decide(true)"><label>검토 의견<textarea v-model="reason" rows="2" maxlength="1000" placeholder="반려할 때는 사유가 필요합니다."></textarea></label><div class="actions"><button type="button" class="secondary" :disabled="busy || !reason.trim()" @click="decide(false)">반려</button><button class="primary" :disabled="busy">승인 후 권한 부여</button></div></form>
          <details v-if="detail.evidence?.length"><summary>판단 근거 {{ detail.evidence.length }}건</summary><article v-for="(item,i) in detail.evidence" :key="i" class="evidence"><strong>{{ item.doc_id || '조회한 업무 사실' }} {{ item.article }}</strong><p v-if="item.text">{{ item.text }}</p><pre v-else>{{ JSON.stringify(item,null,2) }}</pre><small>{{ item.source }} {{ item.version }}</small></article></details>
          <details><summary>처리 이력 {{ detail.events?.length || 0 }}건</summary><ol class="timeline"><li v-for="(event,i) in detail.events" :key="i"><strong>{{ event.kind }}</strong><time>{{ when(event.created_at) }}</time><pre>{{ JSON.stringify(event.payload,null,2) }}</pre></li></ol></details><p v-if="detail.agent_mode==='demo'" class="mode-note">데모 모드 · 실제 LLM 대신 재현 가능한 시나리오 해석기를 사용했습니다.</p>
        </section><section v-else class="panel empty">요청을 선택하면 분석 근거와 승인 카드가 표시됩니다.</section></div>
      </template>
    </main>
    <footer>UnlockOps · 회사 규정에 근거한 접근 권한 지원 · 모의 SaaS 시연 환경</footer>
  </div>
</template>
