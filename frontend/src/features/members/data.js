import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { invalidateOrgQueries, orgQueryKey } from '../queryKeys'
import { useOrganization, useAuth } from '@clerk/react'

const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30,
  refetchOnWindowFocus: false,
}

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
}

export const useTeachers = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('teachers', orgId),
    queryFn: async () => {
      return apiClient.get('/teachers/')
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}

export const useCurrentMember = ({
  enabled = true,
  refetchInterval = false,
  refetchOnWindowFocus = true,
} = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { getToken, isLoaded, isSignedIn } = useAuth()
  return useQuery({
    queryKey: orgQueryKey('current-member', orgId),
    queryFn: async () => {
      const token = await getToken({ organizationId: orgId })
      if (!token) throw new Error('Organization session token unavailable.')
      return apiClient.get('/members/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
    },
    enabled: Boolean(orgId) && Boolean(isSignedIn) && isLoaded && enabled,
    staleTime: 1000 * 60,
    refetchInterval,
    refetchOnWindowFocus,
  })
}

export const useMembers = ({ includeArchived = false, enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('members', orgId, includeArchived),
    queryFn: async () => {
      return apiClient.get('/members', {
        params: { include_archived: includeArchived },
      })
    },
    enabled: Boolean(orgId) && enabled,
    ...DYNAMIC_OPTS,
  })
}

const invalidateMemberQueries = (queryClient, orgId) => {
  return Promise.all([
    invalidateOrgQueries(queryClient, orgId, ['members', 'current-member', 'teachers', 'eligible-teachers']),
    invalidatePreparationQueries(queryClient, orgId),
  ])
}

export const useCreateMember = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (payload) => {
      return apiClient.post('/members', payload)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

export const useUpdateMember = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ id, ...payload }) => {
      return apiClient.patch(`/members/${id}`, payload)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

export const useRemoveMember = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (id) => {
      return apiClient.post(`/members/${id}/remove`)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

export const useResendMemberInvitation = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (id) => {
      return apiClient.post(`/members/${id}/resend-invitation`)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

export const useRetryMemberSync = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (id) => {
      return apiClient.post(`/members/${id}/retry-sync`)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

export const useRestoreMember = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ id, payload }) => {
      return apiClient.post(`/members/${id}/restore`, payload)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

