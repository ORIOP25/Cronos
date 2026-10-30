import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from '../pages/Dashboard'
import { renderWithRouter } from './testUtils'

const { PreparationDashboard, useDashboard, useDashboardInsights } = vi.hoisted(() => ({
  PreparationDashboard: vi.fn(),
  useDashboard: vi.fn(),
  useDashboardInsights: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useDashboard: () => useDashboard(),
  useDashboardInsights: (options) => useDashboardInsights(options),
}))

vi.mock('../components/AnalyticsHeatmap', () => ({
  default: () => <div data-testid="availability-heatmap" />,
}))

vi.mock('../features/dashboard/PreparationDashboard', () => ({
  PreparationDashboard: (props) => {
    PreparationDashboard(props)
    return <div data-testid="preparation-dashboard" />
  },
}))

function LocationDisplay() {
  const location = useLocation()
  return <output data-testid="location-display">{location.pathname}{location.search}</output>
}

const week = (week_start, values = {}) => ({
  week_start, lessons_due: 0, lessons_given: 0, absence_minutes: 0, substituted_minutes: 0, missing_logs: 0, ...values,
})

const progress = [
  { class_id: 1, course_id: 10, course_name: 'Informática', class_name: 'TI 10', grade_level: 10, overall_percentage: 20, completed_hours: 20, total_hours: 100 },
  { class_id: 2, course_id: 20, course_name: 'Turismo', class_name: 'TUR 11', grade_level: 11, overall_percentage: 60, completed_hours: 60, total_hours: 100 },
]

describe('Dashboard', () => {
  beforeEach(() => {
    useDashboard.mockReturnValue({
      data: {
        mode: 'OPERATIONAL',
        organization_name: 'Escola Exemplo',
        alerts: {
          pending_occurrences_today: 0,
          pending_occurrences_total: 0,
          pending_timesheets: 0,
          pending_drafts: 0,
          active_substitutions_today: 0,
        },
        resources: {
          teachers_count: 2,
          classes_count: 4,
          courses_count: 1,
          subjects_count: 4,
          rooms_count: 5,
          rooms_by_type: { Normal: 3, Oficina: 2 },
        },
        schedule_health: {
          generation_id: 'generation-123',
          blocks_count: 12,
          classes_total: 3,
          classes_archived: 1,
          classes_empty_week: 0,
          week_slots_avg: 3,
          duplicate_teacher_slots: 0,
          teacher_week_slots_avg: 4,
          weekly_fairness_spread: 1,
          duplicate_class_slots: 0,
          annual_class_average: 4,
          annual_teacher_average: 6,
          teachers_total: 2,
          period_start: '2026-09-14',
          period_end: '2027-06-18',
        },
        class_progress: [],
        debts: {
          total_gaps: 0,
          total_hours_owed: 0,
          total_gaps_overdue: 0,
          total_hours_owed_overdue: 0,
          affected_classes_count: 0,
        },
      },
      isLoading: false,
      isError: false,
      error: null,
    })
    useDashboardInsights.mockReturnValue({
      data: {
        weeks: [
          week('2026-10-12', { lessons_due: 10, lessons_given: 8, absence_minutes: 120, substituted_minutes: 60, missing_logs: 1 }),
          week('2026-10-19', { lessons_due: 20, lessons_given: 19, absence_minutes: 60, substituted_minutes: 60, missing_logs: 2 }),
        ],
        debt_weeks: [
          { week_start: '2026-10-12', minutes_by_class: { 1: 60 } },
          { week_start: '2026-10-19', minutes_by_class: { 1: 120, 2: 30 } },
        ],
        teacher_absence_minutes: [{ teacher_id: 7, teacher_name: 'Nuno Ramos', value: 180 }],
        teacher_missing_logs: [{ teacher_id: 8, teacher_name: 'Ana Lima', value: 3 }],
        planned_minutes_to_date: { 1: 3000, 2: 3000 },
      },
      isLoading: false,
      isError: false,
    })
  })

  it('summarises the school and the approved schedule without schedule conflicts', () => {
    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    const overview = within(screen.getByTestId('schedule-health'))
    expect(overview.getByText(/12 blocos, 4 por turma e 6 por professor no ano/)).toBeInTheDocument()
    expect(overview.getByText(/14\/09\/2026/)).toBeInTheDocument()
    expect(overview.getByText(/Inclui 1 turma arquivada/)).toBeInTheDocument()
    expect(overview.getByText('professores por turma').closest('li')).toHaveTextContent('0,5 professores por turma')
    expect(screen.getByTestId('resource-classes')).toHaveTextContent('4')
    expect(overview.getByText('Salas por tipo: Normal: 3 · Oficina: 2')).toBeInTheDocument()
    expect(screen.queryByText(/conflito/i)).not.toBeInTheDocument()
    expect(screen.getByText('Escola Exemplo')).toBeInTheDocument()
  })

  it('uses the shared page padding so the title lines up with other pages', () => {
    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    expect(screen.getByRole('heading', { level: 1 }).closest('.p-4')).not.toBeNull()
  })

  it('renders preparation dashboard when first real schedule is not yet approved', () => {
    useDashboard.mockReturnValue({
      data: {
        mode: 'PREPARATION',
        organization_name: 'Escola Exemplo',
        foundation_status: 'COMPLETED',
        foundation_completed_at: '2025-09-15T00:00:00Z',
        bases: { depth: 6, percentage: 100, complete: true, steps: [] },
      },
      isLoading: false,
    })

    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    expect(screen.getByTestId('preparation-dashboard')).toBeInTheDocument()
    expect(PreparationDashboard).toHaveBeenCalledWith(expect.objectContaining({ autoStartGuide: false }))
    expect(useDashboardInsights).toHaveBeenCalledWith({ enabled: false })
  })

  it('shows evidence that the day is under control when nothing is pending', () => {
    renderWithRouter(<Dashboard />)

    const attention = within(screen.getByTestId('alert-bar'))
    expect(attention.getByText('Sem tarefas pendentes')).toBeInTheDocument()
    expect(attention.getByText('Sumários desta semana: 90%')).toBeInTheDocument()
    expect(attention.getByText('Nenhuma falta de hoje por decidir')).toBeInTheDocument()
  })

  it('lists pending tasks by urgency with their age and opens the right page', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-30T12:00:00'))
    Object.assign(useDashboard().data.alerts, {
      pending_occurrences_today: 1,
      pending_occurrences_total: 7,
      pending_occurrences_upcoming: 2,
      oldest_pending_occurrence_date: '2026-10-26',
      pending_timesheets: 1,
      oldest_pending_timesheet_week: '2026-10-19',
    })
    renderWithRouter(<><Dashboard /><LocationDisplay /></>)
    vi.useRealTimers()

    const attention = within(screen.getByTestId('alert-bar'))
    expect(attention.getByText('8 tarefas pendentes')).toBeInTheDocument()
    const occurrences = screen.getByTestId('alert-occurrences')
    expect(occurrences).toHaveAttribute('data-tone', 'danger')
    expect(occurrences).toHaveTextContent('faltas por decidir')
    expect(occurrences).toHaveTextContent('2 com aula hoje ou mais tarde · a mais antiga tem 4 dias')
    expect(screen.getByTestId('alert-timesheets')).toHaveTextContent('folha de horas por aprovar')
    expect(screen.getByTestId('alert-timesheets')).toHaveTextContent('desde a semana de 19/10/2026')
    expect(attention.queryByText('Nenhuma falta de hoje por decidir')).not.toBeInTheDocument()
    await userEvent.click(occurrences)
    expect(screen.getByTestId('location-display')).toHaveTextContent('/absences?status=OPEN')
  })

  it('compares this week with the previous week and the school year', () => {
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('pulse-given')).toHaveTextContent('95%')
    expect(screen.getByTestId('pulse-given')).toHaveTextContent('▲ 15 p.p. face à semana passada')
    expect(screen.getByTestId('pulse-absences')).toHaveTextContent('1 h')
    expect(screen.getByTestId('pulse-absences')).toHaveTextContent('Semana passada: 2 h')
    expect(screen.getByTestId('pulse-coverage')).toHaveTextContent('100%')
    expect(screen.getByTestId('pulse-coverage')).toHaveTextContent('Média do ano: 67%')
    expect(screen.getByTestId('pulse-missing-logs')).toHaveTextContent('3 no ano letivo')
    expect(screen.getByTestId('pulse-absences')).toHaveAttribute('href', '/absences?date_from=2026-10-19&date_to=2026-10-25')
  })

  it('draws the debt over the year for the school, a course, or a class', async () => {
    useDashboard().data.class_progress = progress
    useDashboard().data.debts = {
      total_gaps: 1, total_hours_owed: 50 / 60, total_hours_owed_overdue: 50 / 60, affected_classes_count: 1,
    }
    renderWithRouter(<><Dashboard /><LocationDisplay /></>)

    const debts = within(screen.getByTestId('debt-summary'))
    expect(debts.getByTestId('debt-trend-latest')).toHaveTextContent('2 h 30 min')
    expect(debts.getByRole('img', { name: /Horas em dívida/ })).toBeInTheDocument()
    expect(debts.getByText(/Hoje: 50 min em 1 furo de 1 turma · 50 min vencidas/)).toBeInTheDocument()

    await userEvent.selectOptions(debts.getByLabelText('Curso'), '20')
    expect(debts.getByTestId('debt-trend-latest')).toHaveTextContent(/^30 min$/)
    await userEvent.selectOptions(debts.getByLabelText('Curso'), 'all')
    await userEvent.selectOptions(debts.getByLabelText('Turma'), '1')
    expect(debts.getByTestId('debt-trend-latest')).toHaveTextContent(/^2 h$/)

    await userEvent.click(debts.getByRole('button', { name: /Ver detalhes/ }))
    expect(screen.getByTestId('location-display')).toHaveTextContent('/absences?tab=debts&class_id=1')
  })

  it('ranks the classes and teachers that need follow-up', () => {
    useDashboard().data.class_progress = progress
    renderWithRouter(<Dashboard />)

    const behind = within(screen.getByTestId('ranking-classes-behind'))
    expect(behind.getByRole('link', { name: /TI 10/ })).toHaveAttribute('href', '/courses/10/classes/1')
    expect(behind.getByText('20% dado, 50% previsto até hoje')).toBeInTheDocument()
    expect(behind.queryByText('TUR 11')).not.toBeInTheDocument()
    const debt = within(screen.getByTestId('ranking-classes-debt'))
    expect(debt.getAllByRole('link').map((link) => link.textContent)).toEqual(['TI 102 h', 'TUR 1130 min'])
    expect(within(screen.getByTestId('ranking-teacher-absences')).getByRole('link', { name: /Nuno Ramos/ })).toHaveAttribute('href', '/schedules?teacherId=7')
    expect(within(screen.getByTestId('ranking-teacher-logs')).getByText('aulas terminadas sem sumário')).toBeInTheDocument()
  })

  it('marks where each class should be today in the curricular progress', () => {
    useDashboard().data.class_progress = progress
    renderWithRouter(<Dashboard />)

    const rows = screen.getAllByTestId('class-progress-row')
    expect(within(rows[0]).getByRole('img', { name: 'Previsto até hoje: 50%' })).toBeInTheDocument()
  })

  it('shows a compact class preview and expands all classes without losing filters', async () => {
    useDashboard().data.class_progress = Array.from({ length: 18 }, (_, i) => ({
      class_id: i, course_id: 1, course_name: 'Informática', class_name: `Turma ${i}`, grade_level: 10, overall_percentage: i * 5,
    }))
    renderWithRouter(<Dashboard />)
    expect(screen.getAllByTestId('class-progress-row')).toHaveLength(5)
    await userEvent.click(screen.getByRole('button', { name: 'Ver todas as turmas (18)' }))
    expect(screen.getAllByTestId('class-progress-row')).toHaveLength(18)
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar menos turmas' }))
    expect(screen.getAllByTestId('class-progress-row')).toHaveLength(5)
  })

  it('keeps the daily tasks visible when the trends fail to load', async () => {
    const refetch = vi.fn()
    useDashboardInsights.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error('boom'), refetch })
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('alert-bar')).toBeInTheDocument()
    expect(screen.getByText('Não foi possível carregar as tendências')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(refetch).toHaveBeenCalled()
  })
})
