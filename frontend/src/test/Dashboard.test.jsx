import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from '../pages/Dashboard'
import { renderWithRouter } from './testUtils'

const { useDashboard } = vi.hoisted(() => ({
  useDashboard: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useDashboard: () => useDashboard(),
}))

vi.mock('../components/AnalyticsHeatmap', () => ({
  default: () => <div data-testid="availability-heatmap" />,
}))

describe('Dashboard', () => {
  beforeEach(() => {
    useDashboard.mockReturnValue({
      data: {
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

  it('renders schedule health returned by the dashboard API', () => {
    renderWithRouter(<Dashboard />, { initialEntries: ['/dashboard'] })

    expect(screen.getByTestId('schedule-health')).toBeInTheDocument()
    expect(screen.getByText(/12 blocos no total/i)).toBeInTheDocument()
  })
})
