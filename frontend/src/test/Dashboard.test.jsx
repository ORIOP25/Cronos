// Ficheiro: frontend/src/test/Dashboard.test.jsx
/**
 * TESTES — Dashboard V1 Command Center
 * Valida renderização dos widgets, estados (loading/empty/error), e navegação.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import Dashboard from '../pages/Dashboard'
import { renderWithRouter } from './testUtils'
import { useAuthStore } from '../store'
import * as schoolHooks from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', async () => {
  const actual = await vi.importActual('../hooks/useSchoolData')
  return {
    ...actual,
    useDashboard: vi.fn(),
  }
})

function mockDashboard(data = null, isLoading = false, isError = false, error = null) {
  schoolHooks.useDashboard.mockReturnValue({ data, isLoading, isError, error })
}

const completeData = {
  alerts: {
    pending_occurrences_today: 3,
    pending_timesheets: 5,
    pending_drafts: 1,
    active_substitutions_today: 2,
  },
  resources: {
    teachers_count: 47,
    classes_count: 12,
    courses_count: 4,
    subjects_count: 95,
    rooms_count: 30,
    rooms_by_type: { normal: 16, lab: 8, gym: 3, art: 3 },
  },
  schedule_health: {
    generation_id: 'abc123def456',
    blocks_count: 1247,
    classes_total: 6,
    classes_empty_week: 2,
    week_slots_avg: 28.5,
    duplicate_teacher_slots: 0,
    duplicate_class_slots: 0,
    weekly_fairness_spread: 3.2,
    teacher_week_slots_avg: 22.1,
  },
  class_progress: [
    { class_id: 1, class_name: '1ºA TGPSI', course_id: 1, course_name: 'TGPSI', grade_level: 10, overall_percentage: 38, completed_hours: 19, total_hours: 50 },
    { class_id: 2, class_name: '2ºA TGPSI', course_id: 1, course_name: 'TGPSI', grade_level: 11, overall_percentage: 91, completed_hours: 45.5, total_hours: 50 },
  ],
  debts: {
    total_gaps: 12,
    total_hours_owed: 34,
    total_gaps_overdue: 4,
    total_hours_owed_overdue: 8,
    affected_classes_count: 4,
    as_of_date: '2026-05-04',
  },
  organization_name: 'Escola Teste',
}

const allClearData = {
  ...completeData,
  alerts: {
    pending_occurrences_today: 0,
    pending_timesheets: 0,
    pending_drafts: 0,
    active_substitutions_today: 0,
  },
}

describe('Dashboard V1 Command Center', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: { email: 'admin@escola.pt', role: 'admin', teacherId: null, orgId: 1, orgName: 'Escola Teste' },
    })
  })

  it('renderiza header e todos os widgets com dados completos', () => {
    mockDashboard(completeData)
    renderWithRouter(<Dashboard />)

    expect(screen.getByText('Painel de')).toBeInTheDocument()

    // AlertBar
    expect(screen.getByTestId('alert-bar')).toBeInTheDocument()
    expect(screen.getByTestId('alert-ocorrencias')).toBeInTheDocument()
    expect(screen.getByTestId('alert-timesheets')).toBeInTheDocument()
    expect(screen.getByTestId('alert-drafts')).toBeInTheDocument()
    expect(screen.getByTestId('alert-substituicoes')).toBeInTheDocument()

    // Other widgets
    expect(screen.getByTestId('schedule-health')).toBeInTheDocument()
    expect(screen.getByTestId('class-progress')).toBeInTheDocument()
    expect(screen.getByTestId('debt-summary')).toBeInTheDocument()
    expect(screen.getByTestId('resource-counts')).toBeInTheDocument()

    // QuickActions visible since there are alerts
    expect(screen.getByTestId('action-ocorrencias')).toBeInTheDocument()
    expect(screen.getByTestId('action-timesheets')).toBeInTheDocument()
    expect(screen.getByTestId('action-drafts')).toBeInTheDocument()
  })

  it('mostra skeletons durante loading', () => {
    mockDashboard(null, true)
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('alert-bar')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-health')).toBeInTheDocument()
    expect(screen.getByTestId('class-progress')).toBeInTheDocument()
    expect(screen.getByTestId('debt-summary')).toBeInTheDocument()
    expect(screen.getByTestId('resource-counts')).toBeInTheDocument()
  })

  it('mostra alerta de erro quando a API falha', () => {
    mockDashboard(null, false, true, { message: 'Erro de rede' })
    renderWithRouter(<Dashboard />)

    expect(screen.getByText(/Erro ao carregar o dashboard/)).toBeInTheDocument()
  })

  it('mostra empty state quando não há geração de horário', () => {
    mockDashboard({ ...completeData, schedule_health: null })
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('schedule-health-empty')).toBeInTheDocument()
    expect(screen.getByText(/Nenhum horário gerado/)).toBeInTheDocument()
  })

  it('mostra empty state quando não há progresso', () => {
    mockDashboard({ ...completeData, class_progress: [] })
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('class-progress-empty')).toBeInTheDocument()
    expect(screen.getByText(/Sem dados de progresso/)).toBeInTheDocument()
  })

  it('esconde botões condicionais do QuickActions quando tudo a zero', () => {
    mockDashboard(allClearData)
    renderWithRouter(<Dashboard />)

    expect(screen.queryByTestId('action-ocorrencias')).not.toBeInTheDocument()
    expect(screen.queryByTestId('action-timesheets')).not.toBeInTheDocument()
    expect(screen.queryByTestId('action-drafts')).not.toBeInTheDocument()

    // "Gerar novo horário" deve estar sempre visível
    expect(screen.getByTestId('action-gerar-horario')).toBeInTheDocument()
  })

  it('mostra badge de contagem nos botões QuickActions', () => {
    mockDashboard(completeData)
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('action-ocorrencias')).toBeInTheDocument()
    expect(screen.getByTestId('action-ocorrencias').textContent).toContain('3')
    expect(screen.getByTestId('action-timesheets')).toBeInTheDocument()
    expect(screen.getByTestId('action-timesheets').textContent).toContain('5')
  })

  it('mostra contagens de recursos corretas', () => {
    mockDashboard(completeData)
    renderWithRouter(<Dashboard />)

    expect(screen.getByTestId('resource-teachers')).toHaveTextContent('47')
    expect(screen.getByTestId('resource-classes')).toHaveTextContent('12')
    expect(screen.getByTestId('resource-courses')).toHaveTextContent('4')
  })

  it('mostra ícone de aviso para turmas com baixo progresso', () => {
    mockDashboard(completeData)
    renderWithRouter(<Dashboard />)

    const rows = screen.getAllByTestId('class-progress-row')
    expect(rows.length).toBe(2)

    // First class is 38% - should have warning
    expect(rows[0]).toHaveTextContent('38%')
    expect(screen.getByTestId('warning-icon')).toBeInTheDocument()
  })
})
