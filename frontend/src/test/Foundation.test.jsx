import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, fireEvent, render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import Foundation from '../pages/Foundation'
import { PeriodStep } from '../features/foundation/components/PeriodStep'
import { SlotDurationStep } from '../features/foundation/components/SlotDurationStep'
import { BreakDurationStep } from '../features/foundation/components/BreakDurationStep'
import { LunchStep } from '../features/foundation/components/LunchStep'
import { initialFoundationDraftValues } from '../features/foundation/foundationModel'

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

  it('renders numeric validation feedback as visible block feedback', () => {
    const values = { ...initialFoundationDraftValues }
    const fieldErrors = {
      repair_stability_window_days: 'Estabilidade inválida',
      slot_duration_minutes: 'Duração inválida',
      break_duration_minutes: 'Intervalo inválido',
      lunch_min_duration_minutes: 'Almoço inválido',
    }

    const { container } = render(
      <>
        <PeriodStep values={values} fieldErrors={fieldErrors} onChange={vi.fn()} />
        <SlotDurationStep values={values} fieldErrors={fieldErrors} onChange={vi.fn()} />
        <BreakDurationStep values={values} fieldErrors={fieldErrors} onChange={vi.fn()} />
        <LunchStep values={values} fieldErrors={fieldErrors} onChange={vi.fn()} />
      </>,
    )

    for (const id of [
      'repair_stability_window_days-feedback',
      'slot_duration_minutes-feedback',
      'break_duration_minutes-feedback',
      'lunch_min_duration_minutes-feedback',
    ]) {
      expect(container.querySelector(`#${id}`)).toHaveClass('d-block')
    }
    expect(screen.getByText('Duração Mínima de Almoço *')).toBeInTheDocument()
    expect(screen.queryByText(/Duração Mínima de Almoço \(Minutos\)/i)).not.toBeInTheDocument()
    expect(screen.getAllByText('Minutos')).toHaveLength(3)
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
      fireEvent.click(screen.getByRole('button', { name: /seguinte|ignorar/i }))
      expect(await screen.findByText(step)).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole('checkbox', { name: /confirmo que revi/i }))
    fireEvent.click(screen.getByRole('button', { name: /^ativar escola$/i }))
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

  it('sends a boolean for automatic holidays and allows disabling after a save error', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'IN_PROGRESS',
          foundation_completed_at: null,
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
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
    })
    apiClient.put.mockImplementation((url, payload) => {
      if (payload.data.automatic_holidays_enabled === true) {
        return Promise.reject({
          response: { status: 503, data: { detail: { code: 'HOLIDAY_SYNC_FAILED', message: 'sync failed' } } },
        })
      }
      return Promise.resolve({ version: payload.expected_version + 1 })
    })

    renderFoundation()
    await screen.findByText(/1. Período do Ano Letivo/i)

    for (const step of [
      /2. Dias de Funcionamento Letivo/i,
      /3. Horário de Abertura e Encerramento/i,
      /4. Duração dos Blocos de Aulas/i,
      /5. Intervalos entre Blocos/i,
      /6. Período e Duração de Almoço/i,
      /7. Pré-visualização da Grelha Horária/i,
      /8. Feriados e Pausas Letivas/i,
    ]) {
      fireEvent.click(screen.getByRole('button', { name: /seguinte|ignorar/i }))
      await screen.findByText(step)
    }

    const checkbox = screen.getByRole('checkbox', { name: /feriados automáticos/i })
    fireEvent.click(checkbox)
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/foundation/draft', expect.objectContaining({
      data: expect.objectContaining({ automatic_holidays_enabled: true }),
    })))
    await screen.findByText(/não foi possível guardar o rascunho|sync failed/i)
    expect(checkbox).not.toBeDisabled()

    fireEvent.click(await screen.findByRole('button', { name: /desativar feriados automáticos e guardar/i }))
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/foundation/draft', expect.objectContaining({
      data: expect.objectContaining({ automatic_holidays_enabled: false }),
    })))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /feriados automáticos/i })).not.toBeChecked())
  })

  it('recovers a holiday sync failure after a period edit and keeps the new dates', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'IN_PROGRESS',
          foundation_completed_at: null,
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
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
          automatic_holidays_enabled: true,
        },
      })
    })
    apiClient.put.mockImplementation((_url, payload) => {
      if (payload.data.school_hard_end_date === '2026-08-31' && payload.data.automatic_holidays_enabled) {
        return Promise.reject({
          response: { status: 503, data: { detail: { code: 'HOLIDAY_SYNC_FAILED', message: 'sync failed' } } },
        })
      }
      return Promise.resolve({ version: payload.expected_version + 1 })
    })

    renderFoundation()
    const hardEndDate = await screen.findByDisplayValue('2026-07-31')
    fireEvent.change(hardEndDate, { target: { value: '2026-08-31' } })

    await screen.findByRole('button', { name: /desativar feriados automáticos e guardar/i })
    fireEvent.click(screen.getByRole('button', { name: /desativar feriados automáticos e guardar/i }))

    await waitFor(() => expect(apiClient.put).toHaveBeenLastCalledWith('/foundation/draft', expect.objectContaining({
      data: expect.objectContaining({
        school_hard_end_date: '2026-08-31',
        automatic_holidays_enabled: false,
      }),
    })))

    fireEvent.click(screen.getByRole('button', { name: /seguinte/i }))
    expect(await screen.findByText(/2. Dias de Funcionamento Letivo/i)).toBeInTheDocument()
  })

  it('recovers an activation sync failure by saving the draft without activating', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'IN_PROGRESS',
          foundation_completed_at: null,
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
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
          automatic_holidays_enabled: true,
        },
      })
    })
    apiClient.put.mockResolvedValue({ version: 1 })
    apiClient.post.mockRejectedValueOnce({
      response: { status: 503, data: { detail: { code: 'HOLIDAY_SYNC_FAILED', message: 'sync failed' } } },
    })

    renderFoundation()
    await screen.findByText(/1. Período do Ano Letivo/i)
    const nextStepHeadings = [
      /2\. Dias de Funcionamento Letivo/i,
      /3\. Horário de Abertura e Encerramento/i,
      /4\. Duração dos Blocos de Aulas/i,
      /5\. Intervalos entre Blocos/i,
      /6\. Período e Duração de Almoço/i,
      /7\. Pré-visualização da Grelha Horária/i,
      /8\. Feriados e Pausas Letivas/i,
      /9\. Confirmação e Ativação da Fundação/i,
    ]

    for (const heading of nextStepHeadings) {
      fireEvent.click(screen.getByRole('button', { name: /seguinte/i }))
      await waitFor(() => expect(screen.getByText(heading)).toBeInTheDocument())
    }

    fireEvent.click(screen.getByRole('checkbox', { name: /confirmo que revi/i }))
    fireEvent.click(screen.getByRole('button', { name: /^ativar escola$/i }))
    await screen.findByRole('button', { name: /desativar feriados automáticos e guardar/i })
    expect(apiClient.post).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /desativar feriados automáticos e guardar/i }))
    await waitFor(() => expect(apiClient.put).toHaveBeenLastCalledWith('/foundation/draft', expect.objectContaining({
      current_step: 9,
      data: expect.objectContaining({ automatic_holidays_enabled: false }),
    })))
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/Feriados automáticos:/i).nextSibling).toHaveTextContent('Desativados')
  })

  it('does not show holiday recovery for a generic save failure', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/foundation/status') {
        return Promise.resolve({
          foundation_status: 'IN_PROGRESS',
          foundation_completed_at: null,
          first_real_schedule_approved_at: null,
          organization_name: 'Escola Foundation',
        })
      }
      return Promise.resolve({ version: 0, current_step: 1, data: {} })
    })
    apiClient.put.mockRejectedValue({
      response: { status: 503, data: { detail: { code: 'OTHER_FAILURE', message: 'other failure' } } },
    })

    renderFoundation()
    const startDate = await screen.findByLabelText(/data de início do ano letivo/i)
    fireEvent.change(startDate, { target: { value: '2025-09-15' } })

    await screen.findByText('other failure')
    expect(screen.queryByRole('button', { name: /desativar feriados automáticos e guardar/i })).not.toBeInTheDocument()
  })
})
