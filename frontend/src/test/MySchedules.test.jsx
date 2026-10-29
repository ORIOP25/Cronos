import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MySchedules from '../pages/MySchedules'

const state = vi.hoisted(() => ({ sameWeekError: false }))

vi.mock('../components/WeekGrid', () => ({
  default: ({ slots }) => <div data-testid="week-grid">{slots.map((slot) => slot.id).join(',')}</div>,
}))
vi.mock('../components/LessonLogModal', () => ({ default: () => null }))
vi.mock('../features/members/data', () => ({ useCurrentMember: () => ({ data: { teacher_id: 7 } }) }))
vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => ({ data: [] }),
  useWeekGridVersions: () => ({ data: null }),
}))
vi.mock('../features/operations/data', () => ({
  useMyTimesheet: () => ({ data: null }),
  useSubmitMyTimesheet: () => ({ isPending: false, mutateAsync: vi.fn() }),
}))
vi.mock('../features/scheduling/data', () => ({
  useTeacherScheduleHorizon: () => ({
    data: {
      min_week_start: '2026-05-04',
      week_start_recommended: '2026-05-04',
      hard_end_date: '2026-05-31',
      active_generation_id: 'generation-a',
    },
    isLoading: false,
    isError: false,
  }),
  useWeekSchedule: (_classId, _teacherId, weekStart) => {
    const isSecondWeek = weekStart === '2026-05-11'
    const isError = isSecondWeek || state.sameWeekError
    return {
      data: [{ id: 'week-a', date: '2026-05-04', timeslot: { day_of_week: 0, start_time: '09:00', end_time: '10:00' } }],
      isFetching: state.sameWeekError,
      error: isError
        ? { response: { status: 503, headers: { 'x-request-id': 'REQWEEK123' } } }
        : null,
      refetch: vi.fn(),
    }
  },
}))

describe('MySchedules query-key failures', () => {
  beforeEach(() => { state.sameWeekError = false })

  it('groups publication and weekly actions while keeping navigation separate from submission', () => {
    render(<MySchedules />)
    const week = screen.getByRole('region', { name: 'Horário semanal' })
    expect(within(week).getByText('Horário publicado')).toBeVisible()
    const navigation = within(week).getByRole('group', { name: 'Navegar entre semanas' })
    expect(within(navigation).getAllByRole('button')).toHaveLength(3)
    expect(within(navigation).queryByRole('button', { name: 'Submeter semana' })).not.toBeInTheDocument()
    expect(within(week).getByRole('button', { name: 'Submeter semana' })).toBeVisible()
  })

  it('retains the lower horizon bound after regrouping the week controls', () => {
    render(<MySchedules />)
    fireEvent.click(screen.getByRole('button', { name: 'Semana anterior' }))
    expect(screen.getByText('Semanas antes de 04/05/2026 estão bloqueadas.')).toBeVisible()
    expect(screen.getByTestId('week-grid')).toHaveTextContent('week-a')
  })

  it('does not show week A data when navigating to failing week B', () => {
    render(<MySchedules />)
    expect(screen.getByTestId('week-grid')).toHaveTextContent('week-a')
    fireEvent.click(screen.getByRole('button', { name: /próxima semana/i }))
    expect(screen.getByText(/não foi possível carregar o seu horário semanal/i)).toBeInTheDocument()
    expect(screen.getByText('REQWEEK123')).toBeInTheDocument()
    expect(screen.queryByTestId('week-grid')).not.toBeInTheDocument()
    expect(screen.queryByText('week-a')).not.toBeInTheDocument()
  })

  it('does not keep stale data visible after a same-week background failure', () => {
    state.sameWeekError = true
    render(<MySchedules />)
    expect(screen.getByText(/não foi possível carregar o seu horário semanal/i)).toBeInTheDocument()
    expect(screen.queryByTestId('week-grid')).not.toBeInTheDocument()
    expect(screen.queryByText('week-a')).not.toBeInTheDocument()
  })
})
