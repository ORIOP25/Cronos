import { useOrganization } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { orgQueryKey } from '../queryKeys'

const STATUS_ROOT = 'onboarding-status'

export function useOnboardingStatus() {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey(STATUS_ROOT, orgId),
    queryFn: () => apiClient.get('/onboarding/status'),
    enabled: Boolean(orgId),
  })
}

export function useCompleteOnboarding() {
  const orgId = useOrganization().organization?.id
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/onboarding', payload),
    onSuccess: () => queryClient.invalidateQueries({
      queryKey: orgQueryKey(STATUS_ROOT, orgId),
    }),
  })
}
