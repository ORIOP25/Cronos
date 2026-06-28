import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import { RequireAdmin, RequireAuth, RequireTeacher } from '../routeGuards'

function renderGuard(ui, initialEntries = ['/protected']) {
  return renderWithProviders(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/protected" element={ui} />
        <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
        <Route path="/my-availability" element={<div data-testid="teacher-route">Teacher</div>} />
        <Route path="/login" element={<div data-testid="login-route">Login</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('RequireAuth', () => {
  beforeEach(() => resetClerkState())

  it('renders children when signed in', () => {
    setClerkState({ isSignedIn: true, isLoaded: true })
    renderGuard(<RequireAuth><div data-testid="child">Content</div></RequireAuth>)
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderGuard(<RequireAuth><div>Content</div></RequireAuth>)
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
  })

  it('redirects to sign-in when signed out', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderGuard(<RequireAuth><div>Content</div></RequireAuth>)
    expect(screen.queryByText('Content')).toBeNull()
  })
})

describe('RequireAdmin', () => {
  beforeEach(() => resetClerkState())

  it('allows org:admin', () => {
    setClerkState({ role: 'org:admin' })
    renderGuard(<RequireAdmin><div data-testid="admin-content">Admin</div></RequireAdmin>)
    expect(screen.getByTestId('admin-content')).toBeInTheDocument()
  })

  it('blocks org:member and redirects to teacher default route', () => {
    setClerkState({ role: 'org:member' })
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.queryByText('Admin')).toBeNull()
    expect(screen.getByTestId('teacher-route')).toBeInTheDocument()
  })

  it('redirects unauthenticated to sign-in', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.queryByText('Admin')).toBeNull()
  })
})

describe('RequireTeacher', () => {
  beforeEach(() => resetClerkState())

  it('allows org:member', () => {
    setClerkState({ role: 'org:member' })
    renderGuard(<RequireTeacher><div data-testid="teacher-content">Teacher</div></RequireTeacher>)
    expect(screen.getByTestId('teacher-content')).toBeInTheDocument()
  })

  it('blocks org:admin and redirects to admin default route', () => {
    setClerkState({ role: 'org:admin' })
    renderGuard(<RequireTeacher><div>Teacher</div></RequireTeacher>)
    expect(screen.queryByText('Teacher')).toBeNull()
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })
})
