import { useState } from 'react'
import { useAuth, useOrganizationList } from '@clerk/react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import apiClient from '../../apiClient'
import { getDefaultRouteForMember } from '../../roleAccess'
import {
  activateAndBootstrapOrganization,
  sessionStoragePort,
} from './activateAndBootstrapOrganization'


export function useCreateActiveOrganization() {
  const { createOrganization, setActive } = useOrganizationList()
  const { getToken } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState(null)

  const run = async (input) => {
    setIsPending(true)
    setError(null)
    try {
      return await activateAndBootstrapOrganization(input, {
        createOrganization,
        setActive,
        getToken,
        storage: sessionStoragePort(),
        bootstrap: async (token) => (
          await apiClient.post('/session/bootstrap', undefined, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).data,
        cacheMember: async (organizationId, result) => {
          queryClient.setQueryData(['current-member', organizationId], {
            ...result.member,
            member_id: result.member.id,
            organization_id: result.organization.id,
          })
          await queryClient.invalidateQueries({
            queryKey: ['current-member', organizationId],
          })
        },
        navigate: (route) => navigate(route, { replace: true }),
        defaultRoute: getDefaultRouteForMember,
      })
    } catch (failure) {
      setError(failure)
      throw failure
    } finally {
      setIsPending(false)
    }
  }

  return { run, isPending, error }
}
