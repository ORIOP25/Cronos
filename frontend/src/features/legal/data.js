import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import legalManifest from './legal-manifest.json'

export const LEGAL_STATUS_KEY = 'legal-status'

export const CURRENT_LEGAL_VERSIONS = Object.freeze({
  terms_version: legalManifest.documents.terms.version,
  dpa_version: legalManifest.documents.dpa.version,
  privacy_version: legalManifest.documents.privacy.version,
})

export const CLERK_LEGAL_METADATA_KEY = 'cronos_legal_versions'

export const CLERK_LEGAL_UNSAFE_METADATA = Object.freeze({
  [CLERK_LEGAL_METADATA_KEY]: Object.freeze({ ...CURRENT_LEGAL_VERSIONS }),
})

export function useLegalStatus({ enabled = true, organizationId } = {}) {
  const orgId = organizationId
  return useQuery({
    queryKey: [LEGAL_STATUS_KEY, orgId],
    queryFn: () => apiClient.get('/legal/status'),
    enabled: Boolean(orgId) && enabled,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}

export function useAcceptLegalDocuments({ organizationId } = {}) {
  const orgId = organizationId
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
