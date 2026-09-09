import { useCallback, useEffect, useRef } from 'react'
import { useUser } from '@clerk/react'
import { useCurrentMember } from '../members/data'
import {
  CLERK_LEGAL_METADATA_KEY,
  CURRENT_LEGAL_VERSIONS,
  useAcceptLegalDocuments,
  useLegalStatus,
} from '../legal/data'
import { hasMemberCapability } from '../../roleAccess'
import { useCreateActiveOrganization } from '../organization/useCreateActiveOrganization'

const ADMIN_ROLES = new Set(['admin', 'org:admin'])

export function getClerkLegalVersions(user) {
  const versions = user?.unsafeMetadata?.[CLERK_LEGAL_METADATA_KEY]
  return versions && typeof versions === 'object' ? versions : {}
}

export function hasCurrentClerkLegalConsent(user) {
  const versions = getClerkLegalVersions(user)
  return Boolean(user?.legalAcceptedAt)
    && Object.entries(CURRENT_LEGAL_VERSIONS).every(([key, value]) => versions[key] === value)
}

export function hasMatchingLegalStatus(user, legalStatus) {
  if (!hasCurrentClerkLegalConsent(user)) return false
  const versions = getClerkLegalVersions(user)
  return Object.keys(CURRENT_LEGAL_VERSIONS).every((key) => legalStatus?.[key] === versions[key])
}

function isMemberBootstrapError(error) {
  return error?.response?.status === 403
}

export function useOnboardingCompletion(organizationState) {
  const { user, isLoaded: userLoaded } = useUser()
  const organizationId = organizationState.organization?.id
  const member = useCurrentMember({ enabled: Boolean(organizationId) })
  const legal = useLegalStatus({ enabled: Boolean(organizationId) && member.isSuccess })
  const acceptance = useAcceptLegalDocuments()
  const bootstrap = useCreateActiveOrganization()
  const bootstrapAttempt = useRef(null)
  const acceptanceAttempt = useRef(null)

  const clerkAdmin = ADMIN_ROLES.has(organizationState.membership?.role)
  const memberAdmin = hasMemberCapability(member.data, 'admin')
  const isAdmin = clerkAdmin || memberAdmin
  const bootstrapRequired = Boolean(isAdmin && organizationId && member.isError && isMemberBootstrapError(member.error))
  const acceptanceKey = `${user?.id || 'anonymous'}:${organizationId || 'none'}`
  const canAutoAccept = Boolean(
    userLoaded
    && member.data
    && isAdmin
    && legal.data?.requires_acceptance
    && hasMatchingLegalStatus(user, legal.data),
  )

  useEffect(() => {
    if (!organizationId || !user?.id) {
      bootstrapAttempt.current = null
      acceptanceAttempt.current = null
      return
    }
    const nextKey = `${user.id}:${organizationId}`
    if (bootstrapAttempt.current && bootstrapAttempt.current !== nextKey) bootstrapAttempt.current = null
    if (acceptanceAttempt.current && !acceptanceAttempt.current.startsWith(nextKey)) acceptanceAttempt.current = null
  }, [organizationId, user?.id])

  useEffect(() => {
    if (!bootstrapRequired || bootstrapAttempt.current === acceptanceKey) return
    bootstrapAttempt.current = acceptanceKey
    void bootstrap.bootstrapActiveOrganization().catch(() => undefined)
  }, [acceptanceKey, bootstrap, bootstrapRequired])

  useEffect(() => {
    if (!canAutoAccept || acceptance.isPending || acceptance.error) return
    const versionKey = Object.values(CURRENT_LEGAL_VERSIONS).join(':')
    const attemptKey = `${acceptanceKey}:${versionKey}`
    if (acceptanceAttempt.current === attemptKey) return
    acceptanceAttempt.current = attemptKey
    void acceptance.mutateAsync({
      acceptance_confirmed: true,
      terms_version: legal.data.terms_version,
      dpa_version: legal.data.dpa_version,
      privacy_version: legal.data.privacy_version,
    }).catch(() => {
      acceptanceAttempt.current = null
    })
  }, [acceptance, acceptanceKey, canAutoAccept, legal.data])

  const retry = useCallback(async () => {
    if (bootstrapRequired || bootstrap.error) {
      bootstrapAttempt.current = null
      try {
        await bootstrap.bootstrapActiveOrganization()
      } catch {
        // The error is exposed through the bootstrap hook for the compact retry state.
      }
      return
    }
    if (acceptance.error) {
      acceptanceAttempt.current = null
      acceptance.reset()
    }
    if (member.isError) {
      await member.refetch()
      return
    }
    if (legal.isError || legal.data?.requires_acceptance) await legal.refetch()
  }, [acceptance, bootstrap, bootstrapRequired, legal, member])

  const error = bootstrap.error || acceptance.error
  const isCompleting = bootstrap.isPending || (canAutoAccept && !acceptance.error)
  const needsManualLegalAcceptance = Boolean(legal.data?.requires_acceptance && member.data && isAdmin && !canAutoAccept)

  return {
    organization: organizationState.organization,
    organizationMembership: organizationState.membership,
    orgLoaded: organizationState.isLoaded,
    user,
    userLoaded,
    member,
    legal,
    acceptance,
    isAdmin,
    bootstrapRequired,
    isCompleting,
    error,
    retry,
    needsManualLegalAcceptance,
  }
}
