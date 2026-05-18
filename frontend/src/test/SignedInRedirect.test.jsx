import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Navigate } from 'react-router-dom'
import { useAuth, useOrganization } from '@clerk/react'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import { getDefaultRouteForRole } from '../roleAccess'

function SignedInRedirect() {
  const { isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <div data-testid="loader">Loading...</div>
  return <Navigate to={getDefaultRouteForRole(membership?.role)} replace />
}

describe('SignedInRedirect', () => {
  beforeEach(() => resetClerkState())

  it('redirects admin to /dashboard', () => {
    setClerkState({ role: 'org:admin' })
    const { container } = renderWithProviders(
      <MemoryRouter><SignedInRedirect /></MemoryRouter>
    )
    expect(screen.queryByTestId('loader')).toBeNull()
  })

  it('redirects teacher to /my-availability', () => {
    setClerkState({ role: 'org:member' })
    const { container } = renderWithProviders(
      <MemoryRouter><SignedInRedirect /></MemoryRouter>
    )
    expect(screen.queryByTestId('loader')).toBeNull()
  })

  it('redirects unknown role to /create-org', () => {
    setClerkState({ role: 'student' })
    const { container } = renderWithProviders(
      <MemoryRouter><SignedInRedirect /></MemoryRouter>
    )
    expect(screen.queryByTestId('loader')).toBeNull()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderWithProviders(
      <MemoryRouter><SignedInRedirect /></MemoryRouter>
    )
    expect(screen.getByTestId('loader')).toBeTruthy()
  })
})
