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
  daily: [
    { day_of_week: 0, current_lessons: 5, proposed_lessons: 6, delta: 1 },
    { day_of_week: 1, current_lessons: 5, proposed_lessons: 6, delta: 1 },
  ],
  affected_availabilities: [
    {
      current_timeslot_id: 11,
      current: { day_of_week: 0, start_time: '08:30', end_time: '09:20' },
      proposed: { day_of_week: 0, start_time: '08:30', end_time: '09:20' },
      match: 'MOVED',
      ambiguous: false,
      requires_decision: true,
      teachers: [{ teacher_id: 5, score: 0 }],
    },
  ],
  affected_constraints: [
    {
      constraint_id: 21,
      current_timeslot_id: 12,
      rule_type: 'CLASS_DAY_OFF',
      rule_payload: { class_id: 1 },
      proposed: null,
      match: 'REMOVED',
      ambiguous: false,
      requires_decision: true,
    },
  ],
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

const PROPOSAL = {
  grid_version_id: 7,
  job_id: 70,
  strategy: 'GRID_CHANGE',
  effective_date: '2026-10-05',
  first_editable_date: '2026-10-05',
  status: 'QUEUED',
  created: true,
}

function mockSchoolConfig({
  publicationState = 'UNPUBLISHED',
  configuration = STORED_CONFIGURATION,
  source = 'VERSION',
  timeslots = [],
  pending = null,
} = {}) {
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
        source,
      })
    }
    if (url === '/timeslots/') return Promise.resolve(timeslots)
    if (url === '/scheduler/status') {
      return Promise.resolve({ school_year_publication_state: publicationState })
    }
    if (url === '/school/grid-changes/pending') return Promise.resolve(pending)
    return Promise.resolve([])
  })
}

async function openGridTab() {
  fireEvent.click(await screen.findByRole('tab', { name: /grelha/i }))
  return screen.findByLabelText('Abertura da Escola')
}

describe('SchoolConfig grid changes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.post.mockResolvedValue({ message: 'Grelha configurada e regenerada com sucesso.' })
  })

  it('loads the stored configuration verbatim, including the closing time', async () => {
    mockSchoolConfig({
      timeslots: [{ day_of_week: 0, start_time: '08:30:00', end_time: '09:20:00' }],
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    expect(screen.getByLabelText('Fecho da Escola')).toHaveValue('18:30')

    fireEvent.click(screen.getByRole('button', { name: 'Personalizar intervalos' }))
    expect(await screen.findByLabelText('Pausa após a aula 2 (09:30-10:20)')).toHaveValue(5)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: {
          start_time: '08:30:00',
          end_time: '18:30:00',
          slot_duration_minutes: 50,
          break_duration_minutes: 10,
          break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
          days_of_week: [0, 1, 2, 3, 4],
        },
      }),
    ))
  })

  it('reconstructs the editor from timeslots when no stored version exists', async () => {
    mockSchoolConfig({
      source: 'BLOCKS',
      configuration: null,
      timeslots: [
        { day_of_week: 1, start_time: '07:30:00', end_time: '08:20:00' },
        { day_of_week: 1, start_time: '08:30:00', end_time: '09:20:00' },
      ],
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    expect(screen.getByLabelText('Abertura da Escola')).toHaveValue('7:30')
    expect(screen.getByLabelText('Fecho da Escola')).toHaveValue('9:20')

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.objectContaining({
        timeslots: expect.objectContaining({
          start_time: '07:30:00',
          end_time: '09:20:00',
          days_of_week: [1],
        }),
      }),
    ))
  })

  it('requires a decision for every affected block before proposing a published grid', async () => {
    mockSchoolConfig({ publicationState: 'PUBLISHED' })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/grid-changes/preview') return Promise.resolve(PREVIEW)
      if (url === '/school/grid-changes') return Promise.resolve(PROPOSAL)
      return Promise.resolve({})
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar alteração/i }))

    expect(await screen.findByText(/primeira data editável/i)).toBeInTheDocument()
    expect(apiClient.post).toHaveBeenCalledWith('/school/grid-changes/preview', {
      timeslots: expect.objectContaining({
        start_time: '08:30:00',
        end_time: '18:30:00',
        break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      }),
    })

    const propose = screen.getByRole('button', { name: /propor alteração/i })
    expect(propose).toBeDisabled()
    expect(screen.getByText(/faltam decisões/i)).toBeInTheDocument()

    const availability = screen.getByText('Segunda 08:30-09:20').closest('fieldset')
    fireEvent.click(within(availability).getByLabelText('Copiar'))
    const constraint = screen.getByText('Regra CLASS_DAY_OFF').closest('fieldset')
    fireEvent.click(within(constraint).getByLabelText('Descartar'))

    await waitFor(() => expect(propose).toBeEnabled())
    fireEvent.click(propose)

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/school/grid-changes', {
      timeslots: expect.objectContaining({
        start_time: '08:30:00',
        end_time: '18:30:00',
      }),
      fingerprint: PREVIEW.fingerprint,
      decisions: [
        { current_timeslot_id: 11, action: 'COPY' },
        { current_timeslot_id: 12, action: 'DISCARD' },
      ],
    }))

    expect(await screen.findByText(/proposta de grelha criada/i)).toBeInTheDocument()
    expect(screen.getByText(/05\/10\/2026/)).toBeInTheDocument()
    expect(screen.getByText(/em fila/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /horários/i })).toHaveAttribute('href', '/schedules')
  })

  it('shows the blockers and disables the proposal when the analysis cannot proceed', async () => {
    mockSchoolConfig({ publicationState: 'PUBLISHED' })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/grid-changes/preview') {
        return Promise.resolve({
          ...PREVIEW,
          affected_availabilities: [],
          affected_constraints: [],
          can_propose: false,
          blockers: ['Existem aulas passadas sem decisão final.'],
        })
      }
      return Promise.resolve({})
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar alteração/i }))

    expect(await screen.findByText('Existem aulas passadas sem decisão final.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /propor alteração/i })).toBeDisabled()
  })

  it('asks the administrator to repeat the preview after a stale conflict', async () => {
    mockSchoolConfig({ publicationState: 'PUBLISHED' })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/grid-changes/preview') return Promise.resolve(PREVIEW)
      if (url === '/school/grid-changes') {
        return Promise.reject({
          response: {
            status: 409,
            data: {
              detail: {
                code: 'GRID_CHANGE_STALE',
                message: 'A análise mudou desde a pré-visualização. Repita a pré-visualização.',
              },
            },
          },
        })
      }
      return Promise.resolve({})
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar alteração/i }))
    await screen.findByText(/primeira data editável/i)

    for (const legend of ['Segunda 08:30-09:20', 'Regra CLASS_DAY_OFF']) {
      const target = screen.getByText(legend).closest('fieldset')
      fireEvent.click(within(target).getByLabelText('Copiar'))
    }
    const propose = screen.getByRole('button', { name: /propor alteração/i })
    expect(propose).toBeEnabled()
    fireEvent.click(propose)

    expect(await screen.findByText(/repita a pré-visualização/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /pré-visualizar alteração/i })).toBeInTheDocument()
  })

  it('keeps the regenerate flow while the school year is unpublished', async () => {
    mockSchoolConfig({ publicationState: 'UNPUBLISHED' })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    fireEvent.click(screen.getByRole('button', { name: /guardar e regenerar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/grid-settings/regenerate',
      expect.anything(),
    ))
    expect(apiClient.post).not.toHaveBeenCalledWith('/school/grid-changes/preview', expect.anything())
  })

  it('shows the pending grid proposal and points cancellation to schedules', async () => {
    mockSchoolConfig({
      publicationState: 'PUBLISHED',
      pending: {
        grid_version_id: 7,
        effective_date: '2026-10-05',
        configuration: STORED_CONFIGURATION,
        job_id: 70,
        job_status: 'RUNNING',
        blocks: [],
      },
    })
    renderWithProviders(<SchoolConfig />)
    await openGridTab()

    expect(await screen.findByText(/proposta de grelha pendente/i)).toBeInTheDocument()
    expect(screen.getByText(/a gerar horário/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /horários/i })).toHaveAttribute('href', '/schedules')
  })
})
