import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

export function useAcceptLegalDocuments() {
  const orgId = useOrganization().organization?.id
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/legal/acceptance', payload),
    onSuccess: (data) => {
      queryClient.setQueryData([LEGAL_STATUS_KEY, orgId], {
        accepted: true,
        requires_acceptance: false,
        terms_version: data.terms_version,
        dpa_version: data.dpa_version,
        accepted_at: data.accepted_at,
      })
      return queryClient.invalidateQueries({ queryKey: [LEGAL_STATUS_KEY, orgId] })
    },
  })
}
