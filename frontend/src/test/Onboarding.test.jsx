import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import Onboarding from '../pages/Onboarding'

vi.mock('../apiClient', () => ({
  default: { get: vi.fn(), post: vi.fn(), interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } }, defaults: { withCredentials: true } },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

function renderOnboarding() {
  return renderWithProviders(<MemoryRouter initialEntries={['/onboarding']}><Routes><Route path="/onboarding" element={<Onboarding />} /><Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} /></Routes></MemoryRouter>)
}

describe('Onboarding', () => {
  beforeEach(() => { resetClerkState(); vi.clearAllMocks(); setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Onboard' }) })

  it('shows the welcome screen and starts the two-step flow', async () => {
    apiClient.get.mockResolvedValueOnce({ onboarding_complete: false, organization_name: 'Escola Onboard' })
    renderOnboarding()
    expect(await screen.findByText(/prepare o cronos/i)).toBeInTheDocument()
    expect(screen.getByText(/escola onboard/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Começar' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
    expect(screen.getByRole('heading', { name: /quando decorre o ano letivo/i })).toBeInTheDocument()
  })

  it('calls status API on mount', async () => {
    apiClient.get.mockResolvedValueOnce({ onboarding_complete: true, organization_name: 'Escola Onboard' })
    renderOnboarding()
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/onboarding/status'))
  })

  it('shows loading state while checking status', () => {
    apiClient.get.mockReturnValueOnce(new Promise(() => {}))
    renderOnboarding()
    expect(screen.getByText(/preparar a sua escola/i)).toBeInTheDocument()
  })

  it('shows a retry state instead of an editable form when status loading fails', async () => {
    apiClient.get.mockRejectedValueOnce(new Error('offline'))
    renderOnboarding()
    expect(await screen.findByRole('button', { name: /tentar novamente/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Começar' })).not.toBeInTheDocument()
  })

  it('redirects to dashboard when onboarding is already complete', async () => {
    apiClient.get.mockResolvedValueOnce({ onboarding_complete: true, organization_name: 'Escola Onboard' })
    renderOnboarding()
    await waitFor(() => expect(screen.getByTestId('dashboard-route')).toBeInTheDocument())
  })

  it('preserves both steps, submits once, and enters the dashboard from success', async () => {
    apiClient.get.mockResolvedValue({ onboarding_complete: false })
    apiClient.post.mockResolvedValue({ ok: true })
    renderOnboarding()
    fireEvent.click(await screen.findByRole('button', { name: 'Começar' }))
    fireEvent.change(screen.getByLabelText(/data de in.cio/i), { target: { value: '2026-09-15' } })
    fireEvent.change(screen.getByLabelText(/data-limite/i), { target: { value: '2027-07-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByRole('heading', { name: /como funciona a pausa de almoço/i })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/início da janela/i), { target: { value: '12:00' } })
    fireEvent.change(screen.getByLabelText(/fim da janela/i), { target: { value: '13:30' } })
    fireEvent.change(screen.getByLabelText(/duração mínima/i), { target: { value: '45' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar e concluir' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/onboarding', { school_start_date: '2026-09-15', school_hard_end_date: '2027-07-31', lunch_start: '12:00', lunch_end: '13:30', lunch_min_duration: 45 }))
    expect(screen.getByRole('heading', { name: /configuração concluída/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Entrar no Cronos' }))
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })
})
