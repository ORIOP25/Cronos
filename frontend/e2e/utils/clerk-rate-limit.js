const RETRY_DELAYS_MS = [5_000, 10_000]

export async function retryClerkRateLimit(operation, wait) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation()
    } catch (error) {
      if (!error?.message?.includes('Too Many Requests') || attempt === RETRY_DELAYS_MS.length) {
        throw error
      }
      await wait(RETRY_DELAYS_MS[attempt])
    }
  }
}
