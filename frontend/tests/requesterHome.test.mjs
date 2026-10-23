import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'
import * as submissions from '../src/problemSubmission.ts'
import * as platforms from '../src/lib/platforms.ts'
import * as status from '../src/lib/status.ts'

// Exercise the actual SFC setup/send and API client. Only routing, polling and HTTP are replaced;
// no browser DOM or additional test dependency is needed for this submission boundary.
const viewUrl = new URL('../src/views/RequesterHome.vue', import.meta.url)
const { descriptor } = parse(readFileSync(viewUrl, 'utf8'))
const viewScript = compileScript(descriptor, { id: 'requester-home-test' }).content
function evaluate(source, imports = {}) {
  const module = { exports: {} }
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  runInNewContext(outputText, {
    module, exports: module.exports, Headers,
    fetch: (...args) => globalThis.fetch(...args),
    require: name => {
      assert.ok(name in imports, `Unexpected import: ${name}`)
      return imports[name]
    },
  })
  return module.exports
}
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')
const draft = 'payment-core 저장소에 push 권한이 필요해요'
const accepted = { id: '40000000-0000-0000-0000-000000000001', status: 'RECEIVED' }
let userNumber = 0
function fixture(t, post, push = async () => {}) {
  const currentUser = vue.ref({ id: `requester-home-${++userNumber}` })
  const requests = [], navigations = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url === '/api/auth/csrf') return Response.json({ token: 'csrf-test', headerName: 'X-XSRF-TOKEN' })
    assert.equal(url, '/api/problems')
    requests.push(options)
    return post(options)
  })
  const api = evaluate(apiSource)
  let composable
  function useProblemSubmission() {
    composable ??= evaluate(readFileSync(new URL('../src/composables/useProblemSubmission.ts', import.meta.url), 'utf8'), {
      '../api': api, '../problemSubmission': submissions, '../session': { currentUser },
    })
    return composable.useProblemSubmission()
  }
  const router = { replace: async () => {}, push: async path => { navigations.push(path); await push(path) } }
  const view = evaluate(viewScript, {
    vue, 'vue-router': { useRouter: () => router, useRoute: () => ({ query: {} }) },
    '../api': api, '../session': { currentUser },
    '../composables/useProblemSubmission': { useProblemSubmission },
    '../lib/platforms': platforms, '../lib/status': status,
    '../lib/polling': { usePolling: () => ({ restart() {} }) },
    // 이 테스트는 구 계정(v1) 접수 경로를 본다. v2 접수는 #29의 Submission을 그대로 쓴다(phase2.test.mjs).
    '../lib/data': { isV2: () => false, listMine: async () => [], submitV2: async () => null },
    '../components/AppShell.vue': {}, '../components/RequestList.vue': {},
  }).default
  function mount() {
    const form = view.setup({}, { expose() {} })
    form.selected.value = 'GITHUB'
    form.contents.value = `  ${draft}  `
    return form
  }
  return { mount, useProblemSubmission, currentUser, requests, navigations }
}

test('independent composable callers reuse one pending key without depending on a view', async t => {
  const f = fixture(t, () => f.requests.length === 1
    ? Response.json({ message: 'temporary failure' }, { status: 503 })
    : Response.json(accepted, { status: 202 }))
  const input = { platform: 'GITHUB', contents: draft, simulateJiraFailure: false }
  await assert.rejects(f.useProblemSubmission().submitProblem(input), /temporary failure/)
  assert.deepEqual(await f.useProblemSubmission().submitProblem(input), accepted)
  const keys = f.requests.map(request => request.headers.get('Idempotency-Key'))
  assert.ok(keys[0])
  assert.equal(keys[0], keys[1])
  assert.deepEqual(f.navigations, [])
})

test('the composable discards a failed response belonging to a previous user', async t => {
  const f = fixture(t, () => {
    f.currentUser.value = { id: 'another-user' }
    return Response.json({ message: 'previous user failure' }, { status: 503 })
  })
  const result = await f.useProblemSubmission().submitProblem({ platform: 'GITHUB', contents: draft, simulateJiraFailure: false })
  assert.equal(result, null)
  assert.equal(f.requests.length, 1)
})

test('requester home sends CSRF and a stable submission key after failure and remount', async t => {
  const f = fixture(t, () => f.requests.length === 1
    ? Response.json({ message: 'temporary failure' }, { status: 503 })
    : Response.json(accepted, { status: 202 }))
  const first = f.mount()
  await first.send()
  assert.match(first.formError.value, /temporary failure/)
  assert.equal(first.contents.value.trim(), draft)
  const second = f.mount()
  await second.send()
  assert.equal(f.requests.length, 2)
  const key = f.requests[0].headers.get('Idempotency-Key')
  assert.match(key, /^[A-Za-z0-9._:-]{1,128}$/)
  assert.equal(f.requests[1].headers.get('Idempotency-Key'), key)
  assert.equal(f.requests[1].headers.get('X-XSRF-TOKEN'), 'csrf-test')
  assert.equal(f.requests[1].credentials, 'same-origin')
  assert.equal(JSON.parse(f.requests[1].body).contents, draft)
  assert.deepEqual(f.navigations, [`/requests/${accepted.id}`])
  assert.equal(second.contents.value, '')
})

test('a successful acceptance retires the key even if navigation fails', async t => {
  const f = fixture(t, () => Response.json(accepted, { status: 202 }), async () => { throw new Error('navigation failed') })
  await f.mount().send()
  await f.mount().send()
  const keys = f.requests.map(request => request.headers.get('Idempotency-Key'))
  assert.ok(keys[0])
  assert.notEqual(keys[0], keys[1])
})

test('requester home does not submit without an authenticated user', async t => {
  const f = fixture(t, () => Response.json(accepted, { status: 202 }))
  f.currentUser.value = null
  const form = f.mount()
  await form.send()
  assert.equal(f.requests.length, 0)
  assert.match(form.formError.value, /로그인/)
})

test('double clicks keep one snapshot and an old user response cannot navigate', async t => {
  let start, finish
  const started = new Promise(resolve => { start = resolve })
  const released = new Promise(resolve => { finish = resolve })
  const f = fixture(t, async () => { start(); await released; return Response.json(accepted, { status: 202 }) })
  const form = f.mount()
  const first = form.send()
  form.contents.value = '다른 요청 내용'
  await form.send()
  await started
  try {
    assert.equal(f.requests.length, 1)
    assert.equal(JSON.parse(f.requests[0].body).contents, draft)
    f.currentUser.value = { id: 'another-user' }
  } finally { finish() }
  await first
  assert.deepEqual(f.navigations, [])
  assert.equal(form.contents.value, '다른 요청 내용')
})
