import { useQuery } from '@tanstack/react-query'
import { useOrganization } from '@clerk/react'
import apiClient from '../../apiClient'

export const LEGAL_STATUS_KEY = 'legal-status'

export function useLegalStatus({ enabled = true } = {}) {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: [LEGAL_STATUS_KEY, orgId],
    queryFn: () => apiClient.get('/legal/status'),
    enabled: Boolean(orgId) && enabled,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}
