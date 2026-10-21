import { api } from '../api'
import { ProblemSubmission, type AcceptedProblem, type ProblemInput } from '../problemSubmission'
import { currentUser } from '../session'

// Share keys across routed views, including when browser storage is unavailable.
const submissions = new ProblemSubmission()

/** Submit a problem with its authenticated user's retry identity. The view owns presentation. */
export function useProblemSubmission() {
  async function submitProblem(input: ProblemInput): Promise<AcceptedProblem | null> {
    const requesterId = currentUser.value?.id
    if (!requesterId) throw new Error('로그인이 끝났어요. 다시 로그인해 주세요.')

    try {
      const accepted = await submissions.submit(requesterId, input, (body, key) => api<AcceptedProblem>('/problems', {
        method: 'POST', headers: { 'Idempotency-Key': key }, body,
      }))
      // A completed request from an earlier login must not affect the current user's screen.
      return currentUser.value?.id === requesterId ? accepted : null
    } catch (error) {
      if (currentUser.value?.id !== requesterId) return null
      throw error
    }
  }

  return { submitProblem }
}
