import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SchoolConfig from '../pages/SchoolConfig'
import { renderWithProviders } from './testUtils'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { withCredentials: true },
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

describe('SchoolConfig scheduler settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/settings/') {
        return Promise.resolve({
          school_start_date: '2026-09-15',
          school_hard_end_date: '2027-07-31',
          repair_stability_window_days: 14,
        })
      }
      if (url === '/school/grid-settings/') {
        return Promise.resolve({
          lunch_window_start: '12:00:00',
          lunch_window_end: '14:00:00',
          lunch_min_duration_minutes: 60,
        })
      }
      if (url === '/timeslots/') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiClient.post.mockResolvedValue({ message: 'Grelha configurada e regenerada com sucesso.' })
  })

  it('requests data only for the active configuration section', async () => {
    renderWithProviders(<SchoolConfig />)

    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/school/settings/'))
    expect(apiClient.get).not.toHaveBeenCalledWith('/school/calendar-events/')
    expect(apiClient.get).not.toHaveBeenCalledWith('/school/grid-settings/')
    expect(apiClient.get).not.toHaveBeenCalledWith('/timeslots/')

    fireEvent.click(screen.getByRole('tab', { name: /calendário/i }))
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/school/calendar-events/'))
    expect(apiClient.get).not.toHaveBeenCalledWith('/school/grid-settings/')
  })

  it('uses automatic holidays and does not expose a manual import action', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(screen.getByRole('tab', { name: /calendário/i }))
    const automaticHolidays = await screen.findByRole('checkbox', { name: /feriados automáticos/i })

    expect(automaticHolidays).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /importar feriados/i })).not.toBeInTheDocument()
  })

  it('submits hard boundaries and accepts a zero-day stability window', async () => {
    renderWithProviders(<SchoolConfig />)

    const repairWindow = await screen.findByLabelText(/janela de estabilidade/i)
    expect(screen.queryByLabelText(/fim previsto|data preferida/i)).not.toBeInTheDocument()

    fireEvent.change(repairWindow, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar alterações/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /guardar alterações/i }).at(-1))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/school/settings/', {
        school_start_date: '2026-09-15',
        school_hard_end_date: '2027-07-31',
        repair_stability_window_days: 0,
      })
    })
  })

  it('keeps edited settings and offers holiday recovery after a sync failure', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/settings/') {
        return Promise.resolve({
          school_start_date: '2026-09-15',
          school_hard_end_date: '2027-07-31',
          repair_stability_window_days: 14,
          automatic_holidays_enabled: true,
        })
      }
      return Promise.resolve([])
    })
    apiClient.post.mockRejectedValueOnce({
      response: { status: 503, data: { detail: { code: 'HOLIDAY_SYNC_FAILED', message: 'sync failed' } } },
    })

    renderWithProviders(<SchoolConfig />)
    const endDate = await screen.findByDisplayValue('2027-07-31')
    fireEvent.change(endDate, { target: { value: '2027-08-31' } })
    fireEvent.click(screen.getByRole('button', { name: /^guardar alterações$/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /^guardar alterações$/i }).at(-1))

    const recoveryButton = await screen.findByRole('button', { name: /desativar feriados automáticos e guardar/i })
    expect(screen.getByDisplayValue('2027-08-31')).toBeInTheDocument()
    fireEvent.click(recoveryButton)

    await waitFor(() => expect(apiClient.post).toHaveBeenLastCalledWith('/school/settings/', {
      school_start_date: '2026-09-15',
      school_hard_end_date: '2027-08-31',
      repair_stability_window_days: 14,
      automatic_holidays_enabled: false,
    }))
    expect(await screen.findByText(/guardado com os feriados automáticos desativados/i)).toBeInTheDocument()
  })

  it('does not offer holiday recovery for a generic settings error', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/settings/') {
        return Promise.resolve({
          school_start_date: '2026-09-15',
          school_hard_end_date: '2027-07-31',
          repair_stability_window_days: 14,
          automatic_holidays_enabled: true,
        })
      }
      return Promise.resolve([])
    })
    apiClient.post.mockRejectedValueOnce({
      response: { status: 503, data: { detail: { code: 'OTHER_FAILURE', message: 'other failure' } } },
    })

    renderWithProviders(<SchoolConfig />)
    fireEvent.click(await screen.findByRole('button', { name: /^guardar alterações$/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /^guardar alterações$/i }).at(-1))

    await screen.findByText('other failure')
    expect(screen.queryByRole('button', { name: /desativar feriados automáticos e guardar/i })).not.toBeInTheDocument()
  })

  it('submits the grid with one atomic request and shows one success', async () => {
    const { queryClient } = renderWithProviders(<SchoolConfig />)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByLabelText(/duração da aula/i)
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledTimes(1)
      expect(apiClient.post).toHaveBeenCalledWith('/school/grid-settings/regenerate', {
        grid_settings: {
          lunch_window_start: '12:00:00',
          lunch_window_end: '14:00:00',
          lunch_min_duration_minutes: 60,
        },
        timeslots: {
          start_time: '08:00:00',
          end_time: '18:00:00',
          slot_duration_minutes: 50,
          break_duration_minutes: 10,
          days_of_week: [0, 1, 2, 3, 4],
        },
      })
    })
    expect(screen.getAllByRole('alert').filter((alert) => alert.textContent.includes('Grelha configurada'))).toHaveLength(1)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['org-grid-settings', 1],
      ['timeslots', 1],
      ['my-availability', 1],
      ['scheduler-status', 1],
      ['scheduler-current-draft', 1],
    ]))
  })

  it('shows only the API error and keeps the button reusable after a conflict', async () => {
    apiClient.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Use Recomeçar Ano Letivo.' } } })
    const { queryClient } = renderWithProviders(<SchoolConfig />)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByLabelText(/duração da aula/i)
    const button = screen.getByRole('button', { name: /guardar e regenerar/i })
    fireEvent.click(button)

    expect(await screen.findByText('Use Recomeçar Ano Letivo.')).toBeInTheDocument()
    expect(screen.queryByText('Grelha configurada e regenerada com sucesso.')).not.toBeInTheDocument()
    await waitFor(() => expect(button).toBeEnabled())
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('does not request or show success while the form is invalid', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    fireEvent.change(await screen.findByLabelText(/duração da aula/i), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    expect(await screen.findByText(/preencha uma grelha válida/i)).toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('hydrates the real grid and blocks an irregular persisted grid', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/timeslots/') return Promise.resolve([
        { day_of_week: 0, start_time: '07:30:00', end_time: '08:20:00' },
        { day_of_week: 1, start_time: '07:30:00', end_time: '08:30:00' },
      ])
      if (url === '/school/grid-settings/') return Promise.resolve(null)
      return Promise.resolve([])
    })
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))

    expect(await screen.findByText(/irregular/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar e regenerar/i })).toBeDisabled()
  })
})
