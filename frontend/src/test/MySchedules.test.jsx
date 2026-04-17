import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import MySchedules from '../pages/MySchedules'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'
import * as schoolHooks from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', () => ({
  useTeacherScheduleHorizon: vi.fn(),
  useWeekSchedule: vi.fn(),
  useTimeslots: vi.fn(),
}))

vi.mock('../components/WeekGrid', () => ({
  default: ({ slots, weekStart, isOperationalEnabled }) => (
    <div>
      <div>WEEK_GRID_{weekStart}</div>
      <div>SLOTS_{slots.length}</div>
      <div>OPERATIONAL_{String(isOperationalEnabled)}</div>
      {slots.map((slot) => (
        <div key={slot.schedule_output_id}>{slot.subject?.name}</div>
      ))}
    </div>
  ),
}))

const baseTimeslot = {
  id: 1,
  day_of_week: 0,
  start_time: '09:00',
  end_time: '11:00',
}

const buildSlot = () => ({
  schedule_output_id: 1001,
  date: '2026-04-21',
  timeslot: baseTimeslot,
  subject: { id: 10, name: 'Programacao' },
  teacher: { id: 22, name: 'Prof. Joana' },
  class_info: { id: 1, name: '10TGPSI' },
  is_past: false,
  occurrence_status: null,
  hours_given: null,
})

const setupHooks = ({ horizonData, horizonError = null, weekSlots = [] }) => {
  schoolHooks.useTeacherScheduleHorizon.mockReturnValue({
    data: horizonData,
    isLoading: false,
    isError: Boolean(horizonError),
    error: horizonError,
  })

  schoolHooks.useWeekSchedule.mockReturnValue({
    data: weekSlots,
    isFetching: false,
    isError: false,
  })

  schoolHooks.useTimeslots.mockReturnValue({
    data: [baseTimeslot],
  })
}

const renderPage = () => renderWithProviders(<MySchedules />)

describe('MySchedules page (Ponto 4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'teacher@escola.pt',
        role: 'teacher',
        teacherId: 22,
        orgId: 1,
      },
    })
  })

  it('renderiza grelha pessoal sem controlos administrativos', async () => {
    setupHooks({
      horizonData: {
        min_week_start: '2025-09-01',
        week_start_recommended: '2026-04-20',
        hard_end_date: '2026-07-31',
        active_generation_id: 'gen-abc-1234',
      },
      weekSlots: [buildSlot()],
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Programacao')).toBeInTheDocument()
    })

    expect(screen.getByText('OPERATIONAL_false')).toBeInTheDocument()
    expect(screen.queryByLabelText('Turma')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Professor')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Gerar Horário/i })).not.toBeInTheDocument()
  })

  it('configura polling de horizonte em 30 segundos', () => {
    setupHooks({
      horizonData: {
        min_week_start: '2025-09-01',
        week_start_recommended: '2026-04-20',
        hard_end_date: '2026-07-31',
        active_generation_id: 'gen-abc-1234',
      },
      weekSlots: [buildSlot()],
    })

    renderPage()

    expect(schoolHooks.useTeacherScheduleHorizon).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        refetchInterval: 30000,
      })
    )
  })

  it('invalida cache semanal quando a geracao ativa muda', async () => {
    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries').mockResolvedValue(undefined)

    let mutableHorizon = {
      min_week_start: '2025-09-01',
      week_start_recommended: '2026-04-20',
      hard_end_date: '2026-07-31',
      active_generation_id: 'gen-old-1111',
    }

    schoolHooks.useTeacherScheduleHorizon.mockImplementation(() => ({
      data: mutableHorizon,
      isLoading: false,
      isError: false,
      error: null,
    }))

    schoolHooks.useWeekSchedule.mockReturnValue({
      data: [buildSlot()],
      isFetching: false,
      isError: false,
    })

    schoolHooks.useTimeslots.mockReturnValue({
      data: [baseTimeslot],
    })

    const view = renderPage()

    await waitFor(() => {
      expect(screen.getByText('Programacao')).toBeInTheDocument()
    })
    expect(invalidateSpy).not.toHaveBeenCalled()

    mutableHorizon = {
      ...mutableHorizon,
      active_generation_id: 'gen-new-2222',
    }

    view.rerender(<MySchedules />)

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled()
      expect(screen.getByText('Horário sincronizado com a publicação ativa mais recente.')).toBeInTheDocument()
    })

    invalidateSpy.mockRestore()
  })

  it('bloqueia avanço além do hard_end_date com feedback claro', async () => {
    setupHooks({
      horizonData: {
        min_week_start: '2026-04-20',
        week_start_recommended: '2026-04-20',
        hard_end_date: '2026-04-24',
        active_generation_id: null,
      },
      weekSlots: [],
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Próxima semana' }))

    expect(screen.getByText('Semanas após 24/04/2026 estão bloqueadas.')).toBeInTheDocument()
  })

  it('mostra empty state quando não existem blocos na semana', () => {
    setupHooks({
      horizonData: {
        min_week_start: '2025-09-01',
        week_start_recommended: '2026-04-20',
        hard_end_date: '2026-07-31',
        active_generation_id: null,
      },
      weekSlots: [],
    })

    renderPage()

    expect(screen.getByText('Não existem blocos planeados para a semana selecionada.')).toBeInTheDocument()
  })

  it('mapeia erro 404 de horizonte para mensagem operacional', () => {
    setupHooks({
      horizonData: undefined,
      horizonError: { response: { status: 404 } },
      weekSlots: [],
    })

    renderPage()

    expect(
      screen.getByText(
        'Não existe horizonte semanal configurado para a organização. Contacte um admin para validar o ano letivo ativo.'
      )
    ).toBeInTheDocument()
  })

  it('mapeia erro 429 de horizonte para mensagem de throttling', () => {
    setupHooks({
      horizonData: undefined,
      horizonError: { response: { status: 429 } },
      weekSlots: [],
    })

    renderPage()

    expect(
      screen.getByText(
        'Sincronização temporariamente limitada por excesso de pedidos. Aguarde alguns minutos e volte a tentar.'
      )
    ).toBeInTheDocument()
  })

  it('bloqueia professor sem teacher_id com mensagem operacional clara', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'teacher-sem-perfil@escola.pt',
        role: 'teacher',
        teacherId: null,
        orgId: 1,
      },
    })

    setupHooks({
      horizonData: undefined,
      weekSlots: [],
    })

    renderPage()

    expect(
      screen.getByText('Conta de professor sem perfil associado. Contacte um admin para associar o perfil docente.')
    ).toBeInTheDocument()
  })

  it('bloqueia navegação para semanas antes do limite inferior', () => {
    setupHooks({
      horizonData: {
        min_week_start: '2026-04-20',
        week_start_recommended: '2026-04-20',
        hard_end_date: '2026-07-31',
        active_generation_id: null,
      },
      weekSlots: [],
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Semana anterior' }))

    expect(screen.getByText('Semanas antes de 20/04/2026 estão bloqueadas.')).toBeInTheDocument()
  })

  it('preserva último horizonte válido quando polling devolve erro temporário', async () => {
    let horizonState = {
      min_week_start: '2025-09-01',
      week_start_recommended: '2026-04-20',
      hard_end_date: '2026-07-31',
      active_generation_id: 'gen-ok-1111',
    }
    let horizonErrorState = null

    schoolHooks.useTeacherScheduleHorizon.mockImplementation(() => ({
      data: horizonErrorState ? undefined : horizonState,
      isLoading: false,
      isError: Boolean(horizonErrorState),
      error: horizonErrorState,
    }))

    schoolHooks.useWeekSchedule.mockReturnValue({
      data: [buildSlot()],
      isFetching: false,
      isError: false,
    })
    schoolHooks.useTimeslots.mockReturnValue({ data: [baseTimeslot] })

    const view = renderPage()

    await waitFor(() => {
      expect(screen.getByText('Programacao')).toBeInTheDocument()
    })

    horizonErrorState = { response: { status: 429 } }
    view.rerender(<MySchedules />)

    await waitFor(() => {
      expect(
        screen.getByText('Sincronização do horizonte indisponível temporariamente. A mostrar último estado válido.')
      ).toBeInTheDocument()
      expect(screen.getByText('Programacao')).toBeInTheDocument()
    })
  })
})
