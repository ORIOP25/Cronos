import { useOrganization } from '@clerk/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'

export function invalidatePreparationQueries(queryClient, orgId) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['dashboard', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['readiness-bases', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['prevalidation', orgId] }),
  ])
}

export function usePrevalidation({ fingerprint, enabled = true } = {}) {
  const orgId = useOrganization().organization?.id
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const canCheck = Boolean(orgId) && Boolean(fingerprint) && enabled

  return useQuery({
    queryKey: ['prevalidation', orgId, fingerprint],
    queryFn: async () => {
      try {
        return await apiClient.get('/readiness/prevalidation', { params: { fingerprint } })
      } catch (error) {
        if (error?.response?.status === 409 && error?.response?.data?.detail?.code === 'PREFLIGHT_STALE') {
          void invalidatePreparationQueries(queryClient, orgId)
        }
        throw error
      }
    },
    enabled: canCheck,
    refetchOnWindowFocus: 'always',
    refetchInterval: false,
  })
}
