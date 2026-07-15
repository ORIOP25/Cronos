import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import { SignedInRedirect } from '../routeGuards'

const memberState = vi.hoisted(() => ({
  value: {
    access_status: 'active',
    lifecycle_status: 'active',
    capabilities: ['admin'],
    default_mode: 'admin',
    teacher_id: null,
  },
  loading: false,
  error: null,
}))

vi.mock('../hooks/useSchoolData', () => ({
  useCurrentMember: () => ({
    data: memberState.value,
    isLoading: memberState.loading,
    isError: Boolean(memberState.error),
    error: memberState.error,
    refetch: vi.fn(),
  }),
}))

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
  beforeEach(() => {
    resetClerkState()
    memberState.loading = false
    memberState.error = null
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      teacher_id: null,
    }
  })

  it('redirects admin to /dashboard', () => {
    renderRedirect()
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })

  it('redirects teacher to /my-availability', () => {
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      default_mode: 'teacher',
      teacher_id: 10,
    }
    renderRedirect()
    expect(screen.getByTestId('teacher-route')).toBeInTheDocument()
  })

  it('redirects missing member to /create-org', () => {
    memberState.value = null
    renderRedirect()
    expect(screen.getByTestId('create-org-route')).toBeInTheDocument()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderRedirect()
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
  })
})
