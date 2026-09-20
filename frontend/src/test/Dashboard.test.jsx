import { screen } from '@testing-library/react'
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
          rooms_by_type: {},
        },
        schedule_health: {
          generation_id: 'generation-123',
          blocks_count: 12,
          classes_empty_week: 0,
          week_slots_avg: 3,
          duplicate_teacher_slots: 0,
          teacher_week_slots_avg: 4,
          weekly_fairness_spread: 1,
          duplicate_class_slots: 0,
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
    expect(screen.getByText('Escola Exemplo')).toBeInTheDocument()
    expect(screen.queryByText('Escola: Escola Exemplo')).not.toBeInTheDocument()
  })

  it('renders preparation dashboard when first real schedule is not yet approved', () => {
    useDashboard.mockReturnValue({
      data: {
        mode: 'PREPARATION',
        organization_name: 'Escola Exemplo',
        foundation_status: 'COMPLETED',
        foundation_completed_at: '2025-09-15T00:00:00Z',
        bases: {
          depth: 7,
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
})
