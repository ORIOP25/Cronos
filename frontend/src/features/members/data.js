import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { useOrganization, useAuth } from '@clerk/react'

const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30,
  refetchOnWindowFocus: false,
}

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
}

export const useTeachers = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['teachers', orgId],
    queryFn: async () => {
      return apiClient.get('/teachers/')
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}

export const useCurrentMember = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  const { isLoaded, isSignedIn } = useAuth()
  return useQuery({
    queryKey: ['current-member', orgId],
    queryFn: async () => {
      return apiClient.get('/members/me')
    },
    enabled: Boolean(orgId) && Boolean(isSignedIn) && isLoaded && enabled,
    staleTime: 1000 * 60,
  })
}

export const useMembers = ({ includeArchived = false, enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['members', orgId, includeArchived],
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
    queryClient.invalidateQueries({ queryKey: ['members', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['current-member', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['teachers', orgId] }),
  ])
}

export const useCreateMember = () => {
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
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ id, payload }) => {
      return apiClient.post(`/members/${id}/restore`, payload)
    },
    onSuccess: () => invalidateMemberQueries(queryClient, orgId),
  })
}

