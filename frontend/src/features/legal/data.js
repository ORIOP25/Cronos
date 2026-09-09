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
    onSuccess: async (acceptance) => {
      queryClient.setQueryData([LEGAL_STATUS_KEY, orgId], (current) => ({
        ...current,
        accepted: true,
        requires_acceptance: false,
        terms_version: acceptance.terms_version,
        dpa_version: acceptance.dpa_version,
        privacy_version: acceptance.privacy_version,
        accepted_at: acceptance.accepted_at,
      }))
      await queryClient.invalidateQueries({ queryKey: [LEGAL_STATUS_KEY, orgId] })
    },
  })
}
