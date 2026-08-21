import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import Foundation from '../pages/Foundation'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { withCredentials: true },
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

function renderFoundation() {
  return renderWithProviders(
    <MemoryRouter initialEntries={['/foundation']}>
      <Routes>
        <Route path="/foundation" element={<Foundation />} />
        <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Foundation', () => {
  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Foundation' })
  })

  it('shows the foundation wizard and steps through to activation', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'IN_PROGRESS',
          foundation_completed_at: null,
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
      if (url === '/foundation/draft') {
        return Promise.resolve({
          version: 0,
          current_step: 1,
          data: {
            school_start_date: '2025-09-15',
            school_hard_end_date: '2026-07-31',
            repair_stability_window_days: 14,
            days_of_week: [0, 1, 2, 3, 4],
            opening_time: '08:30',
            closing_time: '17:30',
            slot_duration_minutes: 50,
            break_duration_minutes: 10,
            lunch_window_start: '12:30',
            lunch_window_end: '14:00',
            lunch_min_duration_minutes: 60,
          },
        })
      }
      return Promise.resolve({})
    })
    apiClient.put.mockResolvedValue({ version: 1 })
    apiClient.post.mockResolvedValue({
      foundation_status: 'COMPLETED',
      foundation_completed_at: '2025-09-15T00:00:00Z',
      generated_timeslot_count: 35,
    })

    renderFoundation()

    expect(await screen.findByText(/1. Período do Ano Letivo/i)).toBeInTheDocument()
    expect(await screen.findByDisplayValue('2025-09-15')).toBeInTheDocument()

    for (const step of [
      /2. Dias de Funcionamento Letivo/i,
      /3. Horário de Abertura e Encerramento/i,
      /4. Duração dos Blocos de Aulas/i,
      /5. Intervalos entre Blocos/i,
      /6. Período e Duração de Almoço/i,
      /7. Pré-visualização da Grelha Horária/i,
      /8. Feriados e Pausas Letivas/i,
      /9. Confirmação e Ativação da Fundação/i,
    ]) {
      fireEvent.click(screen.getByRole('button', { name: /seguinte/i }))
      expect(await screen.findByText(step)).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole('checkbox', { name: /confirmo que revi/i }))
    fireEvent.click(screen.getByRole('button', { name: /ativar escola definitivamente/i }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/foundation/complete', {
      expected_version: expect.any(Number),
      confirmed: true,
    }))
    expect(await screen.findByTestId('dashboard-route')).toBeInTheDocument()
  }, 10000)

  it('redirects to dashboard when foundation is already complete', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'COMPLETED',
          foundation_completed_at: '2025-09-15T00:00:00Z',
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
      return Promise.resolve({ version: 1, current_step: 9, data: {} })
    })

    renderFoundation()
    await waitFor(() => expect(screen.getByTestId('dashboard-route')).toBeInTheDocument())
  })
})
