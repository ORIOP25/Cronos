// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import { observeClerkSignIn } from '../../e2e/utils/clerk-rate-limit'

describe('Clerk E2E rate-limit retry', () => {
  it('reports a transient rate limit as an observable incomplete sign-in', async () => {
    const operation = vi.fn().mockRejectedValue(new Error('Too Many Requests'))

    await expect(observeClerkSignIn(operation)).resolves.toBe(false)
    expect(operation).toHaveBeenCalledOnce()
  })

  it('reports a completed sign-in', async () => {
    const operation = vi.fn().mockResolvedValue(undefined)

    await expect(observeClerkSignIn(operation)).resolves.toBe(true)
  })

  it('propagates other authentication failures', async () => {
    const error = new Error('Invalid credentials')

    await expect(observeClerkSignIn(() => Promise.reject(error))).rejects.toBe(error)
  })
})
