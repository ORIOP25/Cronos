import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from '../pages/Dashboard'
import { renderWithRouter } from './testUtils'

const { PreparationDashboard, useDashboard } = vi.hoisted(() => ({
  PreparationDashboard: vi.fn(),
  useDashboard: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useDashboard: () => useDashboard(),
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

describe('Dashboard', () => {
  beforeEach(() => {
    useDashboard.mockReturnValue({
      data: {
        mode: 'OPERATIONAL',
        organization_name: 'Escola Exemplo',
        alerts: {
          pending_occurrences_today: 0,
          pending_timesheets: 0,
          pending_drafts: 0,
          active_substitutions_today: 0,
        },
        resources: {
          teachers_count: 2,
          classes_count: 3,
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
  })

  it('renders schedule health in operational mode when first schedule was approved', () => {
    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    expect(screen.getByTestId('schedule-health')).toBeInTheDocument()
    expect(screen.getByText(/12 blocos no total/i)).toBeInTheDocument()
    expect(screen.getByText('Média anual por turma')).toBeInTheDocument()
    expect(screen.getByText(/3 turmas e 2 professores no horário aprovado/i)).toBeInTheDocument()
    expect(screen.getByText(/Inclui 1 turma arquivada.*catálogo.*turmas ativas/i)).toBeInTheDocument()
    expect(screen.getByText(/14\/09\/2026/)).toBeInTheDocument()
    expect(screen.getByText('Escola Exemplo')).toBeInTheDocument()
    expect(screen.getByTestId('resource-counts')).toHaveTextContent('Normal: 3 · Oficina: 2')
    expect(screen.queryByText('Escola: Escola Exemplo')).not.toBeInTheDocument()
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
        bases: {
          depth: 6,
          percentage: 100,
          complete: true,
          steps: [],
        },
      },
      isLoading: false,
    })

    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    expect(screen.getByTestId('preparation-dashboard')).toBeInTheDocument()
    expect(PreparationDashboard).toHaveBeenCalledWith(
      expect.objectContaining({ autoStartGuide: false }),
    )
  })

  it('requires attention when the approved schedule has conflicts', () => {
    const state = useDashboard()
    state.data.schedule_health.duplicate_teacher_slots = 1
    state.data.schedule_health.duplicate_class_slots = 1
    renderWithRouter(<Dashboard />)
    const attention = within(screen.getByTestId('alert-bar'))
    expect(attention.queryByText('Tudo controlado')).not.toBeInTheDocument()
    expect(attention.getByText('conflitos no horário')).toBeInTheDocument()
  })

  it('identifies conflicting blocks and opens the affected teacher week', async () => {
    useDashboard().data.schedule_health.conflicting_lessons = [{
      lesson_id: 42, teacher_id: 7, teacher_name: 'Nuno Ramos', class_name: 'TAS 10',
      subject_name: 'Matemática', school_date: '2026-10-14',
      starts_at: '2026-10-14T08:00:00Z', ends_at: '2026-10-14T08:50:00Z',
    }]
    renderWithRouter(<><Dashboard /><LocationDisplay /></>)
    await userEvent.click(screen.getByText('Blocos em conflito (1)'))
    const conflict = screen.getByText('TAS 10 · Matemática')
    expect(conflict.tagName).toBe('STRONG')
    expect(conflict.closest('li')).toHaveTextContent('Nuno Ramos · Bloco 42')
    await userEvent.click(screen.getByRole('link', { name: /Abrir semana.*42/ }))
    expect(screen.getByTestId('location-display')).toHaveTextContent('/schedules?teacherId=7&weekStart=2026-10-12')
  })

  it('keeps long conflict lists collapsed and lets the user open and close them', async () => {
    useDashboard().data.schedule_health.conflicting_lessons = Array.from({ length: 30 }, (_, i) => ({
      lesson_id: i, teacher_id: 7, teacher_name: 'Ana', class_name: '10 A', subject_name: 'Português',
      school_date: '2026-10-14', starts_at: '2026-10-14T08:00:00Z', ends_at: '2026-10-14T08:50:00Z',
    }))
    renderWithRouter(<Dashboard />)
    const toggle = screen.getByText('Blocos em conflito (30)')
    expect(toggle.closest('details')).not.toHaveAttribute('open')
    await userEvent.click(toggle)
    expect(toggle.closest('details')).toHaveAttribute('open')
    expect(screen.getAllByRole('link', { name: /Abrir semana do bloco/ })).toHaveLength(30)
    await userEvent.click(toggle)
    expect(toggle.closest('details')).not.toHaveAttribute('open')
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

  it('uses the debt page duration and links to its tab', async () => {
    useDashboard().data.debts = {
      total_gaps: 1, total_hours_owed: 50 / 60, total_hours_owed_overdue: 50 / 60,
      affected_classes_count: 1,
    }
    renderWithRouter(<><Dashboard /><LocationDisplay /></>)
    const debts = within(screen.getByTestId('debt-summary'))
    expect(debts.getByText('50 min')).toBeInTheDocument()
    expect(debts.getByText(/50 min vencidas/)).toBeInTheDocument()
    await userEvent.click(debts.getByRole('button', { name: /Ver detalhes/ }))
    expect(screen.getByTestId('location-display')).toHaveTextContent('/absences?tab=debts')
  })
})
