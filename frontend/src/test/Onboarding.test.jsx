import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import Onboarding from '../pages/Onboarding'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { withCredentials: true },
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

function renderOnboarding() {
  return renderWithProviders(
    <MemoryRouter initialEntries={['/onboarding']}>
      <Routes>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('Onboarding', () => {
  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Onboard' })
  })

  it('shows form when onboarding is incomplete', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: false, organization_name: 'Escola Onboard' } })
    renderOnboarding()
    await waitFor(() => {
      expect(screen.getByText('Escola Onboard')).toBeInTheDocument()
    })
    expect(screen.getByText('Ano Letivo')).toBeInTheDocument()
    expect(screen.queryByLabelText(/fim previsto/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar e come.ar/i })).toBeInTheDocument()
  })

  it('calls status API on mount', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: true, organization_name: 'Escola Onboard' } })
    renderOnboarding()
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/onboarding/status')
    })
  })

  it('shows loading state while checking status', () => {
    apiClient.get.mockReturnValueOnce(new Promise(() => {}))
    renderOnboarding()
    expect(screen.getByText(/preparar a sua escola/i)).toBeInTheDocument()
  })

  it('redirects to dashboard when onboarding is already complete', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: true, organization_name: 'Escola Onboard' } })
    renderOnboarding()

    await waitFor(() => {
      expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
    })
  })

  it('submits school settings and redirects to dashboard', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: false } })
    apiClient.post.mockResolvedValueOnce({ data: { ok: true } })
    renderOnboarding()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /guardar e come.ar/i })).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText(/data de in.cio/i), { target: { value: '2026-09-15' } })
    fireEvent.change(screen.getByLabelText(/fim m.ximo/i), { target: { value: '2027-07-31' } })
    fireEvent.change(screen.getByLabelText(/in.cio do almo.o/i), { target: { value: '12:00' } })
    fireEvent.change(screen.getByLabelText(/fim do almo.o/i), { target: { value: '13:30' } })
    fireEvent.change(screen.getByLabelText(/dura..o m.nima/i), { target: { value: '45' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e come.ar/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/onboarding', {
        school_start_date: '2026-09-15',
        school_hard_end_date: '2027-07-31',
        lunch_start: '12:00',
        lunch_end: '13:30',
        lunch_min_duration: 45,
      })
      expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
    })
  })
})
