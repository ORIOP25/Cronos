import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CalendarSection } from '../features/schoolConfig/SchoolConfigSections'
import { resetClerkState, setClerkState } from './setup'
import { renderWithProviders } from './testUtils'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

const FLOW = {
  id: 7,
  organization_id: 1,
  school_year_id: 3,
  name: 'Estágio 10A',
  start_date: '2026-02-02',
  end_date: '2026-02-13',
  event_type: 'internship_flow',
  source: 'manual',
  class_ids: [1],
}

function settingsResponse() {
  return {
    school_start_date: '2025-09-15',
    school_hard_end_date: '2026-07-31',
    repair_stability_window_days: 14,
  }
}

describe('SchoolConfig internship flows', () => {
  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    setClerkState({ orgId: 1 })
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([FLOW])
      if (url === '/classes/') return Promise.resolve([{ id: 1, name: '10A' }, { id: 2, name: '10B' }])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })
    apiClient.post.mockResolvedValue({})
    apiClient.put.mockResolvedValue({})
    apiClient.delete.mockResolvedValue({ ok: true })
  })

  it('shows the class scope column and loads a flow for editing', async () => {
    renderWithProviders(<CalendarSection />)

    expect(await screen.findByText('Estágio 10A')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Aplica-se a' })).toBeInTheDocument()
    expect(screen.getByText('10A')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /editar estágio 10a/i }))

    expect(screen.getByDisplayValue('Estágio 10A')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '10A' })).toBeChecked()
    expect(screen.getByRole('button', { name: /guardar fluxo/i })).toBeInTheDocument()
  })

  it('keeps event controls visible and calendar guidance optional', async () => {
    renderWithProviders(<CalendarSection />)
    await screen.findByText('Estágio 10A')
    expect(screen.getByLabelText('Nome do evento')).toBeVisible()
    const guidance = screen.getByText('Como funciona o calendário').closest('details')
    expect(guidance).not.toHaveAttribute('open')
    fireEvent.click(screen.getByText('Como funciona o calendário'))
    expect(guidance).toHaveAttribute('open')
  })

  it('marks flows from previous school years as read-only', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') {
        return Promise.resolve([{ ...FLOW, applies_to_current_school_year: false }])
      }
      if (url === '/classes/') return Promise.resolve([{ id: 1, name: '10A' }])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })

    renderWithProviders(<CalendarSection />)

    expect(await screen.findByText('Ano letivo anterior')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar estágio 10a/i })).not.toBeInTheDocument()
  })

  it('does not offer archived classes when creating an internship flow', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([])
      if (url === '/classes/') {
        return Promise.resolve([
          { id: 1, name: '10A', is_archived: false },
          { id: 2, name: '9A arquivada', is_archived: true },
        ])
      }
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })

    renderWithProviders(<CalendarSection />)
    await screen.findByText('Adicionar Evento')
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'internship_flow' } })

    expect(screen.getByRole('checkbox', { name: '10A' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '9A arquivada' })).not.toBeInTheDocument()
  })

  it('asks for confirmation before regenerating the schedule', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([])
      if (url === '/classes/') return Promise.resolve([{ id: 1, name: '10A' }])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/calendar-events/preview') {
        return Promise.resolve({
          requires_confirmation: false,
          confirmation_fingerprint: null,
          affected_lessons: [],
          message: 'Sem aulas afetadas: o horário publicado não muda.',
        })
      }
      return Promise.resolve({})
    })

    renderWithProviders(<CalendarSection />)
    await screen.findByText('Adicionar Evento')

    fireEvent.change(screen.getByLabelText('Nome do evento'), { target: { value: 'Estágio 10A' } })
    fireEvent.change(document.getElementById('eventStart'), { target: { value: '02/02/2026' } })
    fireEvent.change(document.getElementById('eventEnd'), { target: { value: '13/02/2026' } })
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'internship_flow' } })
    fireEvent.click(screen.getByRole('checkbox', { name: '10A' }))
    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar e guardar/i }))

    const regenerateButton = await screen.findByRole('button', { name: /regenerar horário/i })
    expect(apiClient.post).not.toHaveBeenCalledWith('/scheduler/generate', expect.anything())

    fireEvent.click(regenerateButton)
    expect(screen.queryByText('Confirmar alteração do horário')).not.toBeInTheDocument()
    expect(await screen.findByText(/a regeneração analisa o horário/i)).toBeInTheDocument()

    const buttons = screen.getAllByRole('button', { name: /regenerar horário/i })
    fireEvent.click(buttons.at(-1))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/scheduler/generate', {
      idempotency_key: expect.any(String),
      expected_input_revision: expect.any(Number),
    }))
  })

  it('previews affected lessons and sends the confirmed fingerprint', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([])
      if (url === '/classes/') return Promise.resolve([{ id: 1, name: '10A' }])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/calendar-events/preview') {
        return Promise.resolve({
          requires_confirmation: true,
          confirmation_fingerprint: 'fp-1',
          affected_lessons: [
            {
              lesson_id: 5,
              class_id: 1,
              class_name: '10A',
              subject_id: 2,
              subject_name: 'Matemática',
              date: '2026-02-02',
              timeslot_id: 1,
              duration_minutes: 60,
            },
          ],
          message: '1 aula(s) serão retiradas do horário ativo.',
        })
      }
      return Promise.resolve({})
    })

    renderWithProviders(<CalendarSection />)
    await screen.findByText('Adicionar Evento')

    fireEvent.change(screen.getByLabelText('Nome do evento'), { target: { value: 'Estágio 10A' } })
    fireEvent.change(document.getElementById('eventStart'), { target: { value: '02/02/2026' } })
    fireEvent.change(document.getElementById('eventEnd'), { target: { value: '13/02/2026' } })
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'internship_flow' } })
    fireEvent.click(screen.getByRole('checkbox', { name: '10A' }))
    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar e guardar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/school/calendar-events/preview', {
      operation: 'create',
      event_id: null,
      name: 'Estágio 10A',
      start_date: '2026-02-02',
      end_date: '2026-02-13',
      class_ids: [1],
    }))

    expect(await screen.findByText('Confirmar alteração do horário')).toBeInTheDocument()
    expect(screen.getByText('Matemática')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /confirmar e guardar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/school/calendar-events/', {
      name: 'Estágio 10A',
      start_date: '2026-02-02',
      end_date: '2026-02-13',
      class_ids: [1],
      event_type: 'internship_flow',
      confirmation_fingerprint: 'fp-1',
    }))
    expect(await screen.findByText(/1 aula\(s\) saíram do horário ativo/i)).toBeInTheDocument()
  })

  it('creates a flow without confirmation when no lessons are affected', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([])
      if (url === '/classes/') return Promise.resolve([])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/calendar-events/preview') {
        return Promise.resolve({
          requires_confirmation: false,
          confirmation_fingerprint: null,
          affected_lessons: [],
          message: 'Sem aulas afetadas: o horário publicado não muda.',
        })
      }
      return Promise.resolve({})
    })

    renderWithProviders(<CalendarSection />)
    await screen.findByText('Adicionar Evento')

    fireEvent.change(screen.getByLabelText('Nome do evento'), { target: { value: 'Estágio sem turmas' } })
    fireEvent.change(document.getElementById('eventStart'), { target: { value: '02/02/2026' } })
    fireEvent.change(document.getElementById('eventEnd'), { target: { value: '13/02/2026' } })
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'internship_flow' } })
    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar e guardar/i }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/school/calendar-events/', {
      name: 'Estágio sem turmas',
      start_date: '2026-02-02',
      end_date: '2026-02-13',
      class_ids: [],
      event_type: 'internship_flow',
      confirmation_fingerprint: null,
    }))
    expect(screen.queryByText('Confirmar alteração do horário')).not.toBeInTheDocument()
  })

  it('explains a stale preview without changing the schedule', async () => {
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/calendar-events/') return Promise.resolve([])
      if (url === '/classes/') return Promise.resolve([])
      if (url === '/school/settings/') return Promise.resolve(settingsResponse())
      return Promise.resolve([])
    })
    apiClient.post.mockImplementation((url) => {
      if (url === '/school/calendar-events/preview') {
        return Promise.resolve({
          requires_confirmation: false,
          confirmation_fingerprint: null,
          affected_lessons: [],
          message: 'Sem aulas afetadas: o horário publicado não muda.',
        })
      }
      return Promise.reject({
        response: { status: 409, data: { detail: { code: 'CALENDAR_EVENT_STALE', message: 'stale' } } },
      })
    })

    renderWithProviders(<CalendarSection />)
    await screen.findByText('Adicionar Evento')

    fireEvent.change(screen.getByLabelText('Nome do evento'), { target: { value: 'Estágio 10A' } })
    fireEvent.change(document.getElementById('eventStart'), { target: { value: '02/02/2026' } })
    fireEvent.change(document.getElementById('eventEnd'), { target: { value: '13/02/2026' } })
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'internship_flow' } })
    fireEvent.click(screen.getByRole('button', { name: /pré-visualizar e guardar/i }))

    expect(await screen.findByText(/repita a pré-visualização antes de guardar/i)).toBeInTheDocument()
  })
})
