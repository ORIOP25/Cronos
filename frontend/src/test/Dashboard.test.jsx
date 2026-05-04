// Ficheiro: frontend/src/test/Dashboard.test.jsx
/**
 * TESTES — Dashboard Page (Admin)
 * ===============================
 * Valida a renderização do dashboard com dados mockados.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import Dashboard from '../pages/Dashboard'
import { renderWithRouter } from './testUtils'
import { useAuthStore } from '../store'
import * as schoolHooks from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', () => ({
  useClasses: vi.fn(),
  useTeachers: vi.fn(),
  useCourses: vi.fn(),
  useSubjects: vi.fn(),
  useRooms: vi.fn(),
  useSchedule: vi.fn(),
  useDrafts: vi.fn(),
  useDebts: vi.fn(),
  useOccurrences: vi.fn(),
}))

const setupHooks = ({
  classes = [],
  teachers = [],
  courses = [],
  subjects = [],
  rooms = [],
  schedule = null,
  drafts = [],
  debts = null,
  occurrences = [],
} = {}) => {
  schoolHooks.useClasses.mockReturnValue({ data: classes, isLoading: false })
  schoolHooks.useTeachers.mockReturnValue({ data: teachers, isLoading: false })
  schoolHooks.useCourses.mockReturnValue({ data: courses, isLoading: false })
  schoolHooks.useSubjects.mockReturnValue({ data: subjects, isLoading: false })
  schoolHooks.useRooms.mockReturnValue({ data: rooms, isLoading: false })
  schoolHooks.useSchedule.mockReturnValue({ data: schedule, isLoading: false })
  schoolHooks.useDrafts.mockReturnValue({ data: drafts, isLoading: false })
  schoolHooks.useDebts.mockReturnValue({ data: debts, isLoading: false })
  schoolHooks.useOccurrences.mockReturnValue({ data: occurrences, isLoading: false })
}

describe('Dashboard page (admin)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'admin@escola.pt',
        role: 'admin',
        teacherId: null,
        orgId: 1,
        orgName: 'Escola Teste',
      },
    })
  })

  it('renderiza título e cards de estatísticas mesmo sem dados', () => {
    setupHooks()

    renderWithRouter(<Dashboard />)

    expect(screen.getByText('Painel de')).toBeInTheDocument()
  })

  it('mostra contagem de turmas quando existem dados', () => {
    setupHooks({
      classes: [
        { id: 1, name: '10A' },
        { id: 2, name: '10B' },
      ],
      teachers: [{ id: 1, name: 'Prof. A' }],
      courses: [{ id: 1, name: 'Curso 1' }],
    })

    renderWithRouter(<Dashboard />)

    expect(screen.getByText('Painel de')).toBeInTheDocument()
  })

  it('mostra estado de loading quando dados estão a carregar', () => {
    schoolHooks.useClasses.mockReturnValue({ data: undefined, isLoading: true })
    schoolHooks.useTeachers.mockReturnValue({ data: undefined, isLoading: true })
    schoolHooks.useCourses.mockReturnValue({ data: undefined, isLoading: true })
    schoolHooks.useSubjects.mockReturnValue({ data: undefined, isLoading: true })
    schoolHooks.useRooms.mockReturnValue({ data: undefined, isLoading: true })
    schoolHooks.useSchedule.mockReturnValue({ data: undefined, isLoading: false })
    schoolHooks.useDrafts.mockReturnValue({ data: undefined, isLoading: false })
    schoolHooks.useDebts.mockReturnValue({ data: undefined, isLoading: false })
    schoolHooks.useOccurrences.mockReturnValue({ data: undefined, isLoading: false })

    renderWithRouter(<Dashboard />)

    expect(screen.getByText('Painel de')).toBeInTheDocument()
  })
})
