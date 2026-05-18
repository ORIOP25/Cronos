import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Navigate } from 'react-router-dom'
import { useAuth, useOrganization, RedirectToSignIn } from '@clerk/react'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'

function RequireAuth({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <div data-testid="loader">Loading...</div>
  if (!isSignedIn) return <RedirectToSignIn />
  return children
}

function RequireAdmin({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <div data-testid="loader">Loading...</div>
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== 'org:admin') return <Navigate to="/login" />
  return children
}

function RequireTeacher({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <div data-testid="loader">Loading...</div>
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== 'org:member') return <Navigate to="/login" />
  return children
}

describe('RequireAuth', () => {
  beforeEach(() => resetClerkState())

  it('renders children when signed in', () => {
    setClerkState({ isSignedIn: true, isLoaded: true })
    renderWithProviders(
      <MemoryRouter><RequireAuth><div data-testid="child">Content</div></RequireAuth></MemoryRouter>
    )
    expect(screen.getByTestId('child')).toBeTruthy()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderWithProviders(
      <MemoryRouter><RequireAuth><div>Content</div></RequireAuth></MemoryRouter>
    )
    expect(screen.getByTestId('loader')).toBeTruthy()
  })

  it('redirects to sign-in when signed out', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderWithProviders(
      <MemoryRouter><RequireAuth><div>Content</div></RequireAuth></MemoryRouter>
    )
    expect(screen.queryByText('Content')).toBeNull()
  })
})

describe('RequireAdmin', () => {
  beforeEach(() => resetClerkState())

  it('allows org:admin', () => {
    setClerkState({ role: 'org:admin' })
    renderWithProviders(
      <MemoryRouter><RequireAdmin><div data-testid="admin-content">Admin</div></RequireAdmin></MemoryRouter>
    )
    expect(screen.getByTestId('admin-content')).toBeTruthy()
  })

  it('blocks org:member (redirects to /login)', () => {
    setClerkState({ role: 'org:member' })
    const { container } = renderWithProviders(
      <MemoryRouter><RequireAdmin><div>Admin</div></RequireAdmin></MemoryRouter>
    )
    expect(screen.queryByText('Admin')).toBeNull()
  })

  it('redirects unauthenticated to sign-in', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderWithProviders(
      <MemoryRouter><RequireAdmin><div>Admin</div></RequireAdmin></MemoryRouter>
    )
    expect(screen.queryByText('Admin')).toBeNull()
  })
})

describe('RequireTeacher', () => {
  beforeEach(() => resetClerkState())

  it('allows org:member', () => {
    setClerkState({ role: 'org:member' })
    renderWithProviders(
      <MemoryRouter><RequireTeacher><div data-testid="teacher-content">Teacher</div></RequireTeacher></MemoryRouter>
    )
    expect(screen.getByTestId('teacher-content')).toBeTruthy()
  })

  it('blocks org:admin (redirects to /login)', () => {
    setClerkState({ role: 'org:admin' })
    renderWithProviders(
      <MemoryRouter><RequireTeacher><div>Teacher</div></RequireTeacher></MemoryRouter>
    )
    expect(screen.queryByText('Teacher')).toBeNull()
  })
})
