import { useEffect, useMemo } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ApiClientProvider } from '../../ApiClientContext'
import { createQueryClient } from '../../queryClient'
import { createApiClient } from '../../apiClient'
import { createTutorialApiAdapter } from './tutorialApiAdapter'

export function TutorialApiBoundary({ scenario, onDomainMutation, children }) {
  const queryClient = useMemo(() => createQueryClient('tutorial-demo'), [])
  const client = useMemo(() => createApiClient({
    authenticate: false,
    adapter: createTutorialApiAdapter({
      getScenario: () => scenario,
      onDomainMutation,
    }),
  }), [onDomainMutation, scenario])

  useEffect(() => {
    return () => {
      queryClient.clear()
    }
  }, [queryClient])

  return (
    <ApiClientProvider client={client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiClientProvider>
  )
}
