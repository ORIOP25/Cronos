import { useCallback, useState } from 'react'
import { useAuth, useOrganization } from '@clerk/react'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { LEGAL_STATUS_KEY } from '../legal/data'

export function useCreateActiveOrganization() {
  const { organization } = useOrganization()
  const { getToken } = useAuth()
  const queryClient = useQueryClient()
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState(null)

  const bootstrapActiveOrganization = useCallback(async () => {
    const organizationId = organization?.id
    if (!organizationId) throw new Error('Selecione uma organização antes de continuar.')
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
  }, [getToken, organization?.id, queryClient])

  return { bootstrapActiveOrganization, isPending, error }
}
