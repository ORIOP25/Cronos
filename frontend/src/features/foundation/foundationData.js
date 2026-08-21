import { useOrganization } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { orgQueryKey } from '../queryKeys'

const FOUNDATION_STATUS_ROOT = 'foundation-status'
const FOUNDATION_DRAFT_ROOT = 'foundation-draft'

export function useFoundationStatus() {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey(FOUNDATION_STATUS_ROOT, orgId),
    queryFn: () => apiClient.get('/foundation/status'),
    enabled: Boolean(orgId),
  })
}

export function useFoundationDraft() {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey(FOUNDATION_DRAFT_ROOT, orgId),
    queryFn: () => apiClient.get('/foundation/draft'),
    enabled: Boolean(orgId),
  })
}

export function useSaveFoundationDraft() {
  const orgId = useOrganization().organization?.id
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.put('/foundation/draft', payload),
    onSuccess: (data) => {
      queryClient.setQueryData(orgQueryKey(FOUNDATION_DRAFT_ROOT, orgId), data)
      queryClient.invalidateQueries({ queryKey: orgQueryKey(FOUNDATION_STATUS_ROOT, orgId) })
    },
  })
}

export function useCompleteFoundation() {
  const orgId = useOrganization().organization?.id
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/foundation/complete', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgQueryKey(FOUNDATION_STATUS_ROOT, orgId) })
      queryClient.invalidateQueries({ queryKey: orgQueryKey(FOUNDATION_DRAFT_ROOT, orgId) })
      queryClient.invalidateQueries({ queryKey: orgQueryKey('current-member', orgId) })
    },
  })
}
