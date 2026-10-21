import type { Platform } from './api'

export interface ProblemInput {
  platform: Platform
  contents: string
  simulateJiraFailure: boolean
}
export interface AcceptedProblem { id: string; status: 'RECEIVED' }
type PendingStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
type Send = (body: string, key: string) => Promise<AcceptedProblem>
interface Pending { key: string; fingerprint: string }
interface Flight { body: string; promise: Promise<AcceptedProblem> }

/** One key per submission intent. Only a successful acceptance retires an unchanged intent. */
export class ProblemSubmission {
  private readonly storage: () => PendingStorage
  private readonly pending = new Map<string, Pending | null>()
  private readonly flights = new Map<string, Flight>()

  constructor(storage: () => PendingStorage = () => window.sessionStorage) {
    this.storage = storage
  }

  submit(userId: string, input: ProblemInput, send: Send): Promise<AcceptedProblem> {
    // Snapshot before any await: edits while preparing a key cannot change its payload.
    const body = JSON.stringify({platform: input.platform, contents: input.contents, simulateJiraFailure: input.simulateJiraFailure})
    const flight = this.flights.get(userId)
    if (flight) {
      return flight.body === body ? flight.promise : Promise.reject(new Error('이미 접수가 진행 중입니다.'))
    }
    const promise = this.perform(userId, body, send).finally(() => { this.flights.delete(userId) })
    this.flights.set(userId, {body, promise})
    return promise
  }

  private async perform(userId: string, body: string, send: Send): Promise<AcceptedProblem> {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body))
    const fingerprint = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
    const previous = this.read(userId)
    const pending = previous?.fingerprint === fingerprint ? previous : {key: crypto.randomUUID(), fingerprint}
    this.pending.set(userId, pending)
    try { this.storage().setItem(this.storageKey(userId), JSON.stringify(pending)) }
    catch { /* Keep the in-memory key when browser storage is blocked or full. */ }

    const accepted = await send(body, pending.key)
    if (!accepted || typeof accepted.id !== 'string' || !accepted.id || accepted.status !== 'RECEIVED') {
      throw new Error('접수 응답을 확인하지 못했습니다. 같은 내용으로 다시 시도해 주세요.')
    }
    // Cache the cleared state too, so failed storage cleanup cannot revive a completed key in this page.
    this.pending.set(userId, null)
    try {
      const saved = this.storage().getItem(this.storageKey(userId))
      if (saved && JSON.parse(saved)?.key === pending.key) this.storage().removeItem(this.storageKey(userId))
    } catch { /* A successful POST stays successful even when local cleanup fails. */ }
    return accepted
  }

  private read(userId: string): Pending | null {
    if (this.pending.has(userId)) return this.pending.get(userId) ?? null
    try {
      const raw = this.storage().getItem(this.storageKey(userId))
      const saved = raw ? JSON.parse(raw) : null
      if (saved && typeof saved.key === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(saved.key)
          && typeof saved.fingerprint === 'string' && /^[0-9a-f]{64}$/.test(saved.fingerprint)) {
        return {key: saved.key, fingerprint: saved.fingerprint}
      }
    } catch { /* Corrupt or inaccessible pending state is not a valid submission identity. */ }
    return null
  }

  private storageKey(userId: string): string { return `unlockops:problem-submission:${userId}` }
}
