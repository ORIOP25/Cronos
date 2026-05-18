import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

describe('Onboarding', () => {
  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Onboard' })
  })

  it('shows form when onboarding is incomplete', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: false, organization_name: 'Escola Onboard' } })
    renderWithProviders(
      <MemoryRouter><Onboarding /></MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Escola Onboard')).toBeTruthy()
    })
    expect(screen.getByText('Ano Letivo')).toBeTruthy()
    expect(screen.getByText('Guardar e Começar')).toBeTruthy()
  })

  it('calls status API on mount', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: true, organization_name: 'Escola Onboard' } })
    renderWithProviders(
      <MemoryRouter><Onboarding /></MemoryRouter>
    )
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/onboarding/status')
    })
  })

  it('shows loading state while checking status', () => {
    apiClient.get.mockReturnValueOnce(new Promise(() => {}))
    renderWithProviders(
      <MemoryRouter><Onboarding /></MemoryRouter>
    )
    expect(screen.getByText(/preparar a sua escola/i)).toBeTruthy()
  })

  it('shows organization name in title', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: false, organization_name: 'Escola Onboard' } })
    renderWithProviders(
      <MemoryRouter><Onboarding /></MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Escola Onboard')).toBeTruthy()
    })
  })

  it('has Guardar e Começar button', async () => {
    apiClient.get.mockResolvedValueOnce({ data: { onboarding_complete: false } })
    renderWithProviders(
      <MemoryRouter><Onboarding /></MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Guardar e Começar')).toBeTruthy()
    })
  })
})
