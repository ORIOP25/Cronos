import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

  it('uses the shared page spacing and organization heading', () => {
    renderWithProviders(<SchoolConfig />)

    expect(screen.getByRole('heading', { name: 'Test Org' })).toBeInTheDocument()
    expect(screen.getByText('Configuração')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Escola' })).not.toBeInTheDocument()
    expect(screen.queryByText('Organização: Test Org')).not.toBeInTheDocument()
  })

  it('exposes units through accessible suffixes without units in labels', async () => {
    renderWithProviders(<SchoolConfig />)

    const stabilityInput = await screen.findByLabelText('Dias em que o horário não muda')
    expect(stabilityInput).toHaveAttribute('aria-describedby', expect.stringContaining('repairWindow-unit'))
    expect(document.getElementById('repairWindow-unit')).toHaveTextContent('Dias')
    expect(screen.queryByLabelText(/janela de estabilidade \(dias\)/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /grelha/i }))

    for (const field of [
      { label: 'Duração da Aula', unitId: 'slotDuration-unit' },
      { label: 'Intervalo', unitId: 'breakDuration-unit' },
      { label: 'Duração Mínima Almoço', unitId: 'lunchMin-unit' },
    ]) {
      const input = await screen.findByLabelText(field.label)
      expect(input).toHaveAttribute('aria-describedby', expect.stringContaining(field.unitId))
      expect(document.getElementById(field.unitId)).toHaveTextContent('Minutos')
      expect(input.closest('.input-group')?.previousElementSibling).toHaveTextContent(field.label)
    }

    expect(screen.queryByLabelText(/duração da aula \(min\)/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/intervalo \(min\)/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/duração mínima almoço \(min\)/i)).not.toBeInTheDocument()
  })

  it('explains the stability window by what today allows', async () => {
    renderWithProviders(<SchoolConfig />)

    expect(
      await screen.findByText('Com 0, hoje pode mudar; com 1, hoje fica intacto.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/se evita refazer horários/i)).not.toBeInTheDocument()
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

    const repairWindow = await screen.findByLabelText(/dias em que o horário não muda/i)
    expect(screen.getByLabelText(/data preferencial de fim/i)).toBeInTheDocument()

    fireEvent.change(repairWindow, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar alterações/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /guardar alterações/i }).at(-1))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/school/settings/', {
        school_start_date: '2026-09-15',
        school_hard_end_date: '2027-07-31',
        preferred_end_date: null,
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

    renderWithProviders(<SchoolConfig />, { withToaster: true })
    const endDate = await screen.findByDisplayValue('31/07/2027')
    fireEvent.change(endDate, { target: { value: '31/08/2027' } })
    fireEvent.click(screen.getByRole('button', { name: /^guardar alterações$/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /^guardar alterações$/i }).at(-1))

    const recoveryButton = await screen.findByRole('button', { name: /desativar feriados automáticos e guardar/i })
    expect(screen.getByDisplayValue('31/08/2027')).toBeInTheDocument()
    fireEvent.click(recoveryButton)

    await waitFor(() => expect(apiClient.post).toHaveBeenLastCalledWith('/school/settings/', {
      school_start_date: '2026-09-15',
      school_hard_end_date: '2027-08-31',
      preferred_end_date: null,
      repair_stability_window_days: 14,
      automatic_holidays_enabled: false,
    }))
    expect(await within(document.querySelector('[data-rht-toaster]')).findByText(/guardado com os feriados automáticos desativados/i)).toBeInTheDocument()
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

    await screen.findByText('Ocorreu um erro inesperado. Tente novamente.')
    expect(screen.queryByRole('button', { name: /desativar feriados automáticos e guardar/i })).not.toBeInTheDocument()
  })

  it('submits the grid with one atomic request and shows one success', async () => {
    const { queryClient } = renderWithProviders(<SchoolConfig />, { withToaster: true })
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
          break_overrides: [],
          days_of_week: [0, 1, 2, 3, 4],
        },
      })
    })
    const toastHost = document.querySelector('[data-rht-toaster]')
    expect(within(toastHost).getAllByText('Grelha configurada e regenerada com sucesso.')).toHaveLength(1)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['org-grid-settings', 1],
      ['timeslots', 1],
      ['my-availability', 1],
      ['scheduler-status', 1],
      ['scheduler-current-draft', 1],
    ]))
  })

  it('keeps the grid action aligned with the operating days', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByText('Dias de Funcionamento')

    const daysFieldset = screen.getByText('Dias de Funcionamento').closest('fieldset')
    const submitButton = screen.getByRole('button', { name: /guardar e regenerar/i })

    expect(daysFieldset?.closest('.row')).toBe(submitButton.closest('.row'))
    expect(submitButton.closest('.col-md-4')).toHaveClass('d-flex', 'justify-content-md-end', 'align-items-end')
  })

  it('shows only the API error and keeps the button reusable after a conflict', async () => {
    apiClient.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Use Recomeçar Ano Letivo.' } } })
    const { queryClient } = renderWithProviders(<SchoolConfig />, { withToaster: true })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByLabelText(/duração da aula/i)
    const button = screen.getByRole('button', { name: /guardar e regenerar/i })
    fireEvent.click(button)

    expect(await screen.findByText('Atualize a página e tente novamente.')).toBeInTheDocument()
    expect(screen.queryByText('Grelha configurada e regenerada com sucesso.')).not.toBeInTheDocument()
    await waitFor(() => expect(button).toBeEnabled())
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('explains why a published timetable cannot be regenerated instead of a generic refresh', async () => {
    apiClient.post.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'grid_regeneration_blocked',
            message: 'technical details must not be shown',
            reference: 'ABC123DEF456',
          },
        },
      },
    })
    renderWithProviders(<SchoolConfig />, { withToaster: true })

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByLabelText(/duração da aula/i)
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    expect(await screen.findByText(/Não é possível regenerar a grelha enquanto existirem horários/)).toBeInTheDocument()
    expect(screen.queryByText('Atualize a página e tente novamente.')).not.toBeInTheDocument()
    expect(screen.queryByText(/technical details/)).not.toBeInTheDocument()
  })

  it('does not request or show success while the form is invalid', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    fireEvent.change(await screen.findByLabelText(/duração da aula/i), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    expect(await screen.findByText(/preencha uma grelha válida/i)).toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('blocks submit for invalid hours and normalizes typed hours', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    const start = await screen.findByLabelText('Abertura da Escola')
    fireEvent.change(start, { target: { value: '25:00' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    expect(await screen.findByText(/preencha uma grelha válida/i)).toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()

    fireEvent.change(start, { target: { value: '8:30' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: expect.objectContaining({ start_time: '08:30:00' }),
      }),
    ))
  })

  it('compares opening and closing hours in minutes', async () => {
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    fireEvent.change(await screen.findByLabelText('Abertura da Escola'), { target: { value: '9:00' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: expect.objectContaining({ start_time: '09:00:00' }),
      }),
    ))
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

  it('hydrates a variable grid and forwards its overrides on submit', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/timeslots/') {
        return Promise.resolve([
          { day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' },
          { day_of_week: 0, start_time: '10:00:00', end_time: '10:50:00' },
          { day_of_week: 0, start_time: '10:55:00', end_time: '11:45:00' },
        ])
      }
      if (url === '/school/grid-settings/') {
        return Promise.resolve({
          lunch_window_start: '12:00:00',
          lunch_window_end: '14:00:00',
          lunch_min_duration_minutes: 60,
        })
      }
      return Promise.resolve([])
    })
    renderWithProviders(<SchoolConfig />)

    fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
    await screen.findByLabelText(/duração da aula/i)
    expect(screen.getByLabelText('Intervalo')).toHaveValue(10)

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/school/grid-settings/regenerate', {
        grid_settings: {
          lunch_window_start: '12:00:00',
          lunch_window_end: '14:00:00',
          lunch_min_duration_minutes: 60,
        },
        timeslots: {
          start_time: '09:00:00',
          end_time: '11:45:00',
          slot_duration_minutes: 50,
          break_duration_minutes: 10,
          break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
          days_of_week: [0],
        },
      })
    })
  })
})
