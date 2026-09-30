import { useQuery } from '@tanstack/react-query'
import { useOrganization, useAuth } from '@clerk/react'
import { useApiClient } from '../../ApiClientContext'
import { orgQueryKey } from '../queryKeys'

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5,
}

export function invalidatePreparationQueries(queryClient, orgId) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['dashboard', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['readiness-bases', orgId] }),
    queryClient.invalidateQueries({ queryKey: orgQueryKey('scheduler-prevalidation', orgId) }),
    queryClient.invalidateQueries({ queryKey: orgQueryKey('scheduler-status', orgId) }),
  ])
}

export function usePrevalidation({ enabled = true } = {}) {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: orgQueryKey('scheduler-prevalidation', orgId),
    queryFn: async () => apiClient.get('/readiness/prevalidation'),
    enabled: Boolean(orgId) && isLoaded && enabled,
    ...DYNAMIC_OPTS,
  })
}
