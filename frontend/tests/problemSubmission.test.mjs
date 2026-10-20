import test from 'node:test'
import assert from 'node:assert/strict'
import { ProblemSubmission } from '../src/problemSubmission.ts'

const input = () => ({platform: 'GITHUB', contents: 'private request contents', simulateJiraFailure: false})
const accepted = {id: '40000000-0000-0000-0000-000000000001', status: 'RECEIVED'}
function storage() {
  const values = new Map()
  return {
    values,
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  }
}
function latch() {
  let release
  const promise = new Promise(resolve => { release = resolve })
  return {promise, release}
}

test('network and server failures reuse a key; an acknowledged new submission gets a new key', async () => {
  const store = storage(), helper = new ProblemSubmission(() => store), keys = []
  for (const message of ['network failure', 'server 500', 'authentication 401']) {
    await assert.rejects(helper.submit('user-a', input(), async (_, key) => {
      keys.push(key)
      throw new Error(message)
    }), new RegExp(message))
  }
  await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.equal(new Set(keys).size, 1)
  assert.equal(store.values.size, 0)
  await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.notEqual(keys.at(-1), keys[0])
})

test('a reload recovers the key for the same user and transmitted payload without storing the contents', async () => {
  const store = storage(), keys = []
  await assert.rejects(new ProblemSubmission(() => store).submit('user-a', input(), async (_, key) => {
    keys.push(key)
    throw new Error('lost response')
  }))
  assert.equal(store.values.size, 1)
  assert.ok(!JSON.stringify([...store.values.values()]).includes(input().contents))
  await new ProblemSubmission(() => store).submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.equal(keys[0], keys[1])
  assert.equal(store.values.size, 0)
})

test('edited input creates a new intent instead of reusing a key for different input', async () => {
  const store = storage(), helper = new ProblemSubmission(() => store), keys = []
  await assert.rejects(helper.submit('user-a', input(), async (_, key) => { keys.push(key); throw new Error('lost') }))
  await helper.submit('user-a', {...input(), contents: 'edited request'}, async (_, key) => { keys.push(key); return accepted })
  assert.notEqual(keys[0], keys[1])
})

test('pending requests and successful cleanup are scoped to the authenticated user', async () => {
  const store = storage(), keys = []
  await assert.rejects(new ProblemSubmission(() => store).submit('user-a', input(), async (_, key) => {
    keys.push(key); throw new Error('lost')
  }))
  await new ProblemSubmission(() => store).submit('user-b', input(), async (_, key) => { keys.push(key); return accepted })
  assert.notEqual(keys[0], keys[1])
  assert.equal(store.values.size, 1)
  await new ProblemSubmission(() => store).submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.equal(keys[0], keys[2])
  assert.equal(store.values.size, 0)
})

test('double submission shares a single in-flight POST; a changed in-flight draft is rejected', async () => {
  const helper = new ProblemSubmission(() => storage()), started = latch(), finish = latch()
  let calls = 0
  const send = async () => { calls++; started.release(); await finish.promise; return accepted }
  const first = helper.submit('user-a', input(), send)
  const duplicate = helper.submit('user-a', input(), send)
  assert.equal(first, duplicate)
  await started.promise
  try {
    await assert.rejects(helper.submit('user-a', {...input(), contents: 'different'}, send), /진행/)
    assert.equal(calls, 1)
  } finally { finish.release() }
  assert.deepEqual(await first, accepted)
  assert.deepEqual(await duplicate, accepted)
})

test('the payload is snapshotted before asynchronous key generation', async () => {
  const helper = new ProblemSubmission(() => storage()), draft = input()
  let sent
  const response = helper.submit('user-a', draft, async body => { sent = JSON.parse(body); return accepted })
  draft.contents = 'changed while preparing the request'
  await response
  assert.equal(sent.contents, input().contents)
})

test('blocked sessionStorage preserves an in-memory key for retries', async () => {
  const helper = new ProblemSubmission(() => { throw new Error('storage blocked') }), keys = []
  await assert.rejects(helper.submit('user-a', input(), async (_, key) => { keys.push(key); throw new Error('lost') }))
  await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.equal(keys[0], keys[1])
})

test('storage writes and removals failing do not turn a successful POST into a retry', async () => {
  const helper = new ProblemSubmission(() => ({
    getItem: () => null,
    setItem: () => { throw new Error('quota') },
    removeItem: () => { throw new Error('blocked') },
  }))
  const keys = []
  for (let i = 0; i < 2; i++) {
    assert.deepEqual(await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted }), accepted)
  }
  assert.notEqual(keys[0], keys[1])
})

test('corrupted pending storage is ignored safely', async () => {
  const store = storage()
  await assert.rejects(new ProblemSubmission(() => store).submit('user-a', input(), async () => { throw new Error('lost') }))
  const storageKey = [...store.values.keys()][0]
  for (const corrupted of ['not-json', 'null', '{"key":"bad","fingerprint":42}']) {
    store.values.set(storageKey, corrupted)
    assert.deepEqual(await new ProblemSubmission(() => store).submit('user-a', input(), async () => accepted), accepted)
  }
})

test('a failed removal cannot revive a completed key in the current page', async () => {
  const store = storage(), keys = []
  store.removeItem = () => { throw new Error('cleanup blocked') }
  const helper = new ProblemSubmission(() => store)
  for (let i = 0; i < 2; i++) {
    await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  }
  assert.notEqual(keys[0], keys[1])
})

test('an invalid acceptance response leaves the pending key available for recovery', async () => {
  const store = storage(), helper = new ProblemSubmission(() => store), keys = []
  await assert.rejects(helper.submit('user-a', input(), async (_, key) => { keys.push(key); return {status: 'RECEIVED'} }))
  await helper.submit('user-a', input(), async (_, key) => { keys.push(key); return accepted })
  assert.equal(keys[0], keys[1])
})
