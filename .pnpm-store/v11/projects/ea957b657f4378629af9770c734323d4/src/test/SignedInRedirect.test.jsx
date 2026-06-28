import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import { SignedInRedirect } from '../routeGuards'

function renderRedirect() {
  return renderWithProviders(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<SignedInRedirect />} />
        <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
        <Route path="/my-availability" element={<div data-testid="teacher-route">Teacher</div>} />
        <Route path="/create-org" element={<div data-testid="create-org-route">Create Org</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('SignedInRedirect', () => {
  beforeEach(() => resetClerkState())

  it('redirects admin to /dashboard', () => {
    setClerkState({ role: 'org:admin' })
    renderRedirect()
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })

  it('redirects teacher to /my-availability', () => {
    setClerkState({ role: 'org:member' })
    renderRedirect()
    expect(screen.getByTestId('teacher-route')).toBeInTheDocument()
  })

  it('redirects unknown role to /create-org', () => {
    setClerkState({ role: 'student' })
    renderRedirect()
    expect(screen.getByTestId('create-org-route')).toBeInTheDocument()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderRedirect()
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
  })
})
