import { describe, expect, it, vi } from 'vitest'
import { retryClerkRateLimit } from '../../e2e/utils/clerk-rate-limit'

describe('Clerk E2E rate-limit retry', () => {
  it('backs off for transient rate limits and then succeeds', async () => {
    const operation = vi.fn()
      .mockRejectedValueOnce(new Error('Too Many Requests'))
      .mockRejectedValueOnce(new Error('Failed: Too Many Requests'))
      .mockResolvedValue('signed-in')
    const wait = vi.fn().mockResolvedValue(undefined)

    await expect(retryClerkRateLimit(operation, wait)).resolves.toBe('signed-in')
    expect(wait).toHaveBeenNthCalledWith(1, 5_000)
    expect(wait).toHaveBeenNthCalledWith(2, 10_000)
  })

  it('does not retry other authentication failures', async () => {
    const error = new Error('Invalid credentials')
    const wait = vi.fn()

    await expect(retryClerkRateLimit(() => Promise.reject(error), wait)).rejects.toBe(error)
    expect(wait).not.toHaveBeenCalled()
  })
})
