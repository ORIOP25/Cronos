import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { useOrganization } from '@clerk/react'
import { resetClerkState, setClerkState } from './setup'
import {
  hasCurrentClerkLegalConsent,
  hasMatchingLegalStatus,
} from '../features/onboarding/useOnboardingCompletion'
import { useOnboardingCompletion } from '../features/onboarding/useOnboardingCompletion'
import { CURRENT_LEGAL_VERSIONS } from '../features/legal/data'

const memberState = vi.hoisted(() => ({
  data: {
    access_status: 'active',
    lifecycle_status: 'active',
    capabilities: ['admin'],
    default_mode: 'admin',
    foundation_status: 'COMPLETED',
  },
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
}))

const legalState = vi.hoisted(() => ({
  data: {
    accepted: false,
    requires_acceptance: true,
    terms_version: '2026-01',
    dpa_version: '2026-01',
    privacy_version: '2026-01',
  },
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
}))

const acceptance = vi.hoisted(() => ({
  isPending: false,
  error: null,
  mutateAsync: vi.fn().mockResolvedValue({
    terms_version: '2026-01',
    dpa_version: '2026-01',
    privacy_version: '2026-01',
  }),
  reset: vi.fn(),
}))

const bootstrap = vi.hoisted(() => ({
  isPending: false,
  error: null,
  bootstrapActiveOrganization: vi.fn().mockResolvedValue({}),
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => memberState,
}))

vi.mock('../features/legal/data', async (importOriginal) => ({
  ...(await importOriginal()),
  useLegalStatus: () => legalState,
  useAcceptLegalDocuments: () => acceptance,
}))

vi.mock('../features/organization/useCreateActiveOrganization', () => ({
  useCreateActiveOrganization: () => bootstrap,
}))

function wrapper({ children }) {
  return children
}

function userWithVersions(overrides = {}) {
  return {
    legalAcceptedAt: '2026-01-01T00:00:00.000Z',
    unsafeMetadata: { cronos_legal_versions: { ...CURRENT_LEGAL_VERSIONS } },
    ...overrides,
  }
}

function useCompletion() {
  return useOnboardingCompletion(useOrganization())
}

describe('legal consent correlation', () => {
  it('requires Clerk timestamp and all current document versions', () => {
    expect(hasCurrentClerkLegalConsent(userWithVersions())).toBe(true)
    expect(hasCurrentClerkLegalConsent(userWithVersions({ legalAcceptedAt: null }))).toBe(false)
    expect(hasCurrentClerkLegalConsent(userWithVersions({
      unsafeMetadata: { cronos_legal_versions: { ...CURRENT_LEGAL_VERSIONS, dpa_version: 'old' } },
    }))).toBe(false)
  })

  it('also compares the correlated versions with the backend legal status', () => {
    const user = userWithVersions()
    expect(hasMatchingLegalStatus(user, { ...CURRENT_LEGAL_VERSIONS })).toBe(true)
    expect(hasMatchingLegalStatus(user, { ...CURRENT_LEGAL_VERSIONS, terms_version: 'old' })).toBe(false)
  })
})

describe('useOnboardingCompletion', () => {
  beforeEach(() => {
    resetClerkState()
    memberState.data = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      foundation_status: 'COMPLETED',
    }
    memberState.isLoading = false
    memberState.isError = false
    memberState.error = null
    legalState.data = { accepted: false, requires_acceptance: true, ...CURRENT_LEGAL_VERSIONS }
    legalState.isLoading = false
    legalState.isError = false
    legalState.error = null
    acceptance.isPending = false
    acceptance.error = null
    acceptance.mutateAsync.mockClear()
    bootstrap.isPending = false
    bootstrap.error = null
    bootstrap.bootstrapActiveOrganization.mockClear()
  })

  it('automatically accepts once for an administrator with matching Clerk consent', async () => {
    const { rerender } = renderHook(useCompletion, { wrapper })

    await waitFor(() => expect(acceptance.mutateAsync).toHaveBeenCalledTimes(1))
    expect(acceptance.mutateAsync).toHaveBeenCalledWith({
      acceptance_confirmed: true,
      ...CURRENT_LEGAL_VERSIONS,
    })

    rerender()
    expect(acceptance.mutateAsync).toHaveBeenCalledTimes(1)
  })

  it('never accepts on behalf of a non-administrator invitee', async () => {
    setClerkState({ role: 'org:member' })
    memberState.data = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      default_mode: 'teacher',
      teacher_id: 4,
      foundation_status: 'COMPLETED',
    }

    renderHook(useCompletion, { wrapper })
    await act(async () => {})
    expect(acceptance.mutateAsync).not.toHaveBeenCalled()
  })

  it('bootstraps a missing administrator member once and can retry it', async () => {
    memberState.data = undefined
    memberState.isError = true
    memberState.error = { response: { status: 403 } }

    const { result, rerender } = renderHook(useCompletion, { wrapper })
    await waitFor(() => expect(bootstrap.bootstrapActiveOrganization).toHaveBeenCalledTimes(1))
    rerender()
    expect(bootstrap.bootstrapActiveOrganization).toHaveBeenCalledTimes(1)

    await act(async () => { await result.current.retry() })
    expect(bootstrap.bootstrapActiveOrganization).toHaveBeenCalledTimes(2)
  })
})
