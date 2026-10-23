type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
/** Keep one retry identity per user + operation. Only keys/digests go to browser storage. */
export class Submission {
  private pending = new Map<string, { key: string; digest: string } | null>()
  private flights = new Map<string, { body: string; promise: Promise<unknown> }>()
  private storage: () => Store
  constructor(storage: () => Store = () => sessionStorage) {
    this.storage = storage
  }
  submit<T>(
    owner: string,
    kind: 'access' | 'reclaim',
    input: object,
    send: (body: string, key: string) => Promise<T>
  ): Promise<T> {
    const scope = `unlockops:v2:${owner}:${kind}`,
      body = JSON.stringify(input)
    const flight = this.flights.get(scope)
    if (flight)
      return flight.body === body
        ? (flight.promise as Promise<T>)
        : Promise.reject(new Error('접수가 진행 중입니다.'))
    const promise = this.perform(scope, body, send).finally(() => this.flights.delete(scope))
    this.flights.set(scope, { body, promise })
    return promise
  }
  private async perform<T>(scope: string, body: string, send: (body: string, key: string) => Promise<T>) {
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body))
    const digest = [...new Uint8Array(hash)].map((x) => x.toString(16).padStart(2, '0')).join('')
    let prior = this.pending.get(scope)
    if (!this.pending.has(scope)) {
      try {
        prior = JSON.parse(this.storage().getItem(scope) || 'null')
      } catch {
        prior = null
      }
    }
    const value =
      prior?.digest === digest && typeof prior.key === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(prior.key)
        ? prior
        : { key: crypto.randomUUID(), digest }
    this.pending.set(scope, value)
    try {
      this.storage().setItem(scope, JSON.stringify(value))
    } catch {
      /* Memory fallback. */
    }
    const accepted = await send(body, value.key) // Caller validates the response before retiring this key.
    this.pending.set(scope, null)
    try {
      this.storage().removeItem(scope)
    } catch {
      /* Acceptance remains successful. */
    }
    return accepted
  }
}
