import { QueryClient } from '@tanstack/react-query'

function shouldRetryQuery(failureCount, error) {
  if (failureCount >= 2) return false

  const status = error?.response?.status
  return status == null || status === 408 || status === 429 || status >= 500
}

export function createQueryClient(_identity) {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery },
      mutations: { retry: false },
    },
  })
}
