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

const STORED_CONFIGURATION = {
  opening_time: '08:30',
  closing_time: '18:30',
  slot_duration_minutes: 50,
  break_duration_minutes: 10,
  break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
  days_of_week: [0, 1, 2, 3, 4],
}

const PREVIEW = {
  first_editable_date: '2026-10-05',
  current_configuration: STORED_CONFIGURATION,
  proposed_configuration: { ...STORED_CONFIGURATION, closing_time: '19:00' },
  daily: [],
  affected_availabilities: [],
  affected_constraints: [],
  lessons_without_closure: [],
  minutes_completed: 1000,
  minutes_protected: 300,
  minutes_planned_after_boundary: 500,
  minutes_remaining: 1200,
  fingerprint: 'f'.repeat(64),
  pending_grid_version_id: null,
  can_propose: true,
  blockers: [],
}

function mockSchoolConfig({ publicationState = 'UNPUBLISHED', configuration = STORED_CONFIGURATION } = {}) {
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
    if (url === '/school/grid-configuration/') {
      return Promise.resolve({
        version_id: 3,
        effective_date: '2026-09-01',
        state: 'ACTIVE',
        configuration,
        source: 'VERSION',
      })
    }
    if (url === '/scheduler/status') {
      return Promise.resolve({ school_year_publication_state: publicationState })
    }
    if (url === '/school/grid-changes/pending') return Promise.resolve(null)
    return Promise.resolve([])
  })
}

async function openGridTab() {
  fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
  return screen.findByLabelText('Abertura da Escola')
}

async function openBreakModal() {
  fireEvent.click(screen.getByRole('button', { name: 'Personalizar intervalos' }))
  return screen.findByText(/Cada aula pode ter uma pausa diferente/)
}

describe('SchoolConfig break customization modal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.post.mockResolvedValue({ message: 'Grelha configurada e regenerada com sucesso.' })
  })

  it('keeps the break list out of the page and shows the pencil and the indicator', async () => {
    mockSchoolConfig()
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    expect(screen.queryByText(/Pausas entre as aulas do dia/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Pausa após a aula/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Personalizar intervalos' })).toBeInTheDocument()
    expect(screen.getByText('Pausas personalizadas: 1')).toBeInTheDocument()
  })

  it('opens the modal from the pencil and recalculates the timeline while editing', async () => {
    mockSchoolConfig()
    renderWithProviders(<SchoolConfig />)
    await openGridTab()
    await openBreakModal()

    expect(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)')).toHaveValue(10)
    expect(screen.getByLabelText('Pausa após a aula 2 (09:30-10:20)')).toHaveValue(5)
    expect(screen.queryByLabelText('Pausa após a aula 10 (17:25-18:15)')).not.toBeInTheDocument()
    expect(screen.getByText('Aula 3 às 10:25')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '0' },
    })

    expect(screen.getByLabelText('Pausa após a aula 2 (09:20-10:10)')).toHaveValue(5)
    expect(screen.getByText('Aula 3 às 10:15')).toBeInTheDocument()
    const reset = screen.getByRole('button', { name: 'Repor padrão após a aula 1' })
    fireEvent.click(reset)

    expect(screen.getByLabelText('Pausa após a aula 2 (09:30-10:20)')).toHaveValue(5)
    expect(screen.queryByRole('button', { name: 'Repor padrão após a aula 1' })).not.toBeInTheDocument()
  })

  it('reports an invalid duration and lets the administrator correct it', async () => {
    mockSchoolConfig()
    renderWithProviders(<SchoolConfig />)
    await openGridTab()
    await openBreakModal()

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '61' },
    })
    expect(screen.getByText(/Ajuste inválido/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao formulário' }))
    expect(screen.getByRole('alert')).toHaveTextContent('entre 0 e 60 minutos')

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao formulário' }))

    expect(screen.queryByText('Pausa depois da aula')).not.toBeInTheDocument()
    expect(screen.getByText('Pausas personalizadas: 2')).toBeInTheDocument()
  })

  it('shows an adjustment without a following lesson and lets the administrator remove it', async () => {
    mockSchoolConfig({
      configuration: {
        opening_time: '08:30',
        closing_time: '09:20',
        slot_duration_minutes: 50,
        break_duration_minutes: 10,
        break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
        days_of_week: [0],
      },
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()
    await openBreakModal()

    expect(screen.getByText('Ajuste após a aula 2 (sem aula seguinte)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remover ajuste após a aula 2' }))
    expect(screen.queryByText(/sem aula seguinte/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao formulário' }))
    expect(screen.queryByText('Pausas personalizadas: 1')).not.toBeInTheDocument()
  })

  it('discards the draft when the modal is cancelled', async () => {
    mockSchoolConfig()
    renderWithProviders(<SchoolConfig />)
    await openGridTab()
    await openBreakModal()

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByText('Pausa depois da aula')).not.toBeInTheDocument()
    expect(screen.getByText('Pausas personalizadas: 1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: expect.objectContaining({
          break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
        }),
      }),
    ))
  })

  it('applies the draft to the form without calling the API and saves it before publication', async () => {
    mockSchoolConfig()
    renderWithProviders(<SchoolConfig />)
    await openGridTab()
    await openBreakModal()

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao formulário' }))

    expect(apiClient.post).not.toHaveBeenCalled()
    expect(screen.queryByText('Pausa depois da aula')).not.toBeInTheDocument()
    expect(screen.getByText('Pausas personalizadas: 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: expect.objectContaining({
          break_overrides: [
            { after_slot: 1, duration_minutes: 0 },
            { after_slot: 2, duration_minutes: 5 },
          ],
        }),
      }),
    ))
  })

  it('clears the impact preview when the draft is applied after publication', async () => {
    mockSchoolConfig({ publicationState: 'PUBLISHED' })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/grid-changes/preview') return Promise.resolve(PREVIEW)
      return Promise.resolve({})
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar alteração/i }))
    await screen.findByText(/primeira data editável/i)

    await openBreakModal()
    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (08:30-09:20)'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao formulário' }))

    expect(screen.queryByText(/primeira data editável/i)).not.toBeInTheDocument()
    expect(apiClient.post).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar alteração/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenLastCalledWith(
      '/school/grid-changes/preview',
      {
        timeslots: expect.objectContaining({
          break_overrides: [
            { after_slot: 1, duration_minutes: 0 },
            { after_slot: 2, duration_minutes: 5 },
          ],
        }),
      },
    ))
  })
})
