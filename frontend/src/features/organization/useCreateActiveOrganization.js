import { useCallback, useState } from 'react'
import { useAuth, useOrganizationList, useUser } from '@clerk/react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import apiClient from '../../apiClient'
import { getDefaultRouteForMember } from '../../roleAccess'
import { LEGAL_STATUS_KEY } from '../legal/data'
import {
  activateAndBootstrapOrganization,
  sessionStoragePort,
} from './activateAndBootstrapOrganization'


export function useCreateActiveOrganization() {
  const { createOrganization, setActive } = useOrganizationList()
  const { getToken } = useAuth()
  const { user } = useUser()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState(null)

  const bootstrapActiveOrganization = useCallback(async (organizationId) => {
    setIsPending(true)
    setError(null)
    try {
      const token = await getToken({ organizationId, skipCache: true })
      if (!token) throw new Error('A fresh organization session token could not be created.')
      const result = await apiClient.post('/session/bootstrap', undefined, {
        headers: { Authorization: `Bearer ${token}` },
      })
      queryClient.setQueryData(['current-member', organizationId], {
        ...result.member,
        member_id: result.member.id,
        organization_id: result.organization.id,
        foundation_status: result.foundation_status,
      })
      await queryClient.invalidateQueries({ queryKey: [LEGAL_STATUS_KEY, organizationId] })
      return result
    } catch (failure) {
      setError(failure)
      throw failure
    } finally {
      setIsPending(false)
    }
  }, [getToken, queryClient])

  const run = async (input) => {
    setIsPending(true)
    setError(null)
    try {
      return await activateAndBootstrapOrganization({ ...input, userId: user?.id }, {
        createOrganization,
        setActive,
        getToken,
        storage: sessionStoragePort(),
        bootstrap: (token) => apiClient.post('/session/bootstrap', undefined, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        getLegalStatus: (token) => apiClient.get('/legal/status', {
          headers: { Authorization: `Bearer ${token}` },
        }),
        acceptLegalDocuments: (token, payload) => apiClient.post('/legal/acceptance', payload, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        cacheMember: async (organizationId, result) => {
          queryClient.setQueryData(['current-member', organizationId], {
            ...result.member,
            member_id: result.member.id,
            organization_id: result.organization.id,
            foundation_status: result.foundation_status,
          })
        },
        cacheLegalStatus: async (organizationId, result) => {
          queryClient.setQueryData([LEGAL_STATUS_KEY, organizationId], result)
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

  const selectOrganization = async (organizationId) => {
    setIsPending(true)
    setError(null)
    try {
      await setActive({ organization: organizationId })
    } catch (failure) {
      setError(failure)
      throw failure
    } finally {
      setIsPending(false)
    }
  }

  return { run, selectOrganization, bootstrapActiveOrganization, isPending, error }
}
