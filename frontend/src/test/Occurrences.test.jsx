import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Occurrences from '../pages/Occurrences'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'
import * as schoolHooks from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', () => ({
  useOccurrences: vi.fn(),
  useDebts: vi.fn(),
  useUpdateOccurrence: vi.fn(),
  useSubstituteRecommendations: vi.fn(),
  useClasses: vi.fn(),
  useTeachers: vi.fn(),
  useSubjects: vi.fn(),
}))

const defaultOccurrence = {
  id: 101,
  date: '2026-04-10',
  status: 'GIVEN',
  planned_teacher_id: 10,
  executed_teacher_id: 10,
  planned_module_id: 1,
  executed_module_id: 1,
  substitute_teacher_id: null,
  substitute_subject_id: null,
  hours_given: 2,
  decided_by_user_id: null,
  decided_at: null,
}

const setupBaseHooks = () => {
  schoolHooks.useClasses.mockReturnValue({ data: [{ id: 1, name: '10TGPSI' }] })
  schoolHooks.useDebts.mockReturnValue({
    data: { total_gaps: 0, total_hours_owed: 0, items: [] },
    isLoading: false,
    isError: false,
  })
  schoolHooks.useTeachers.mockReturnValue({ data: [{ id: 10, name: 'Prof. Ana' }, { id: 11, name: 'Prof. Bruno' }] })
  schoolHooks.useSubjects.mockReturnValue({ data: [{ id: 200, name: 'Português' }] })
  schoolHooks.useUpdateOccurrence.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  })
  schoolHooks.useSubstituteRecommendations.mockReturnValue({
    data: [{
      rank: 1,
      teacher_id: 11,
      teacher_name: 'Prof. Bruno',
      subject_id: 200,
      subject_name: 'Português',
      substitutions_in_period: 1,
      daily_load_hours: 2,
      days_since_last_substitution: 5,
      justification: 'Menor carga no dia e melhor equilíbrio de substituições.',
    }],
    isLoading: false,
    isError: false,
  })
}

const renderPage = (initialEntries = ['/absences']) => {
  renderWithProviders(
    <MemoryRouter initialEntries={initialEntries}>
      <Occurrences />
    </MemoryRouter>
  )
}

describe('Occurrences page (Passo 5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'admin@escola.pt',
        role: 'admin',
        teacherId: null,
        orgId: 1,
      },
    })
    setupBaseHooks()
  })

  it('lista pendentes e resolvidas com resumo operacional claro', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [
        {
          ...defaultOccurrence,
          id: 102,
          date: '2026-04-11',
          status: 'SUBSTITUTED',
          substitute_teacher_id: 11,
          substitute_subject_id: 200,
          decided_by_user_id: 7,
          decided_at: '2026-04-11T10:00:00Z',
        },
        defaultOccurrence,
      ],
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(screen.getByText('Pendentes (1)')).toBeInTheDocument()
    expect(screen.getByText('Resolvidas (1)')).toBeInTheDocument()
    expect(screen.getAllByText('Pendente de decisão').length).toBeGreaterThanOrEqual(2)

    fireEvent.click(screen.getByRole('button', { name: /Resolvidas \(1\)/i }))

    expect(screen.getByText(/Decidida em/i)).toBeInTheDocument()
    expect(screen.getByText(/Utilizador #7/i)).toBeInTheDocument()
  })

  it('mostra contexto de turma/disciplina e copy atualizado da grelha', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [
        {
          ...defaultOccurrence,
          class_name: '10TGPSI',
          subject_name: 'Português',
          status: 'GAP',
          decided_by_user_id: 7,
          decided_at: '2026-04-11T10:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(screen.getByRole('columnheader', { name: 'Turma' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Disciplina' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Docente Definitivo' })).toBeInTheDocument()
    expect(screen.queryByText('Horas Dadas')).not.toBeInTheDocument()
    const occurrencesTable = screen.getByRole('table')
    expect(within(occurrencesTable).getByText('10TGPSI')).toBeInTheDocument()
    expect(within(occurrencesTable).getByText('Português')).toBeInTheDocument()
  })

  it('abre sem filtros implícitos de data e mostra todas as ocorrências por defeito', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [
        {
          ...defaultOccurrence,
          id: 102,
          status: 'GAP',
          decided_by_user_id: 7,
          decided_at: '2026-04-11T10:00:00Z',
        },
        defaultOccurrence,
      ],
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(schoolHooks.useOccurrences).toHaveBeenCalledWith({
      classId: undefined,
      dateFrom: undefined,
      dateTo: undefined,
    })
    expect(screen.getByText(/Decidida em/i)).toBeInTheDocument()
    expect(screen.getAllByText('Pendente de decisão').length).toBeGreaterThanOrEqual(1)
  })

  it('mostra feedback claro quando não há elegíveis para substituição', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [defaultOccurrence],
      isLoading: false,
      isError: false,
    })
    schoolHooks.useSubstituteRecommendations.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Decidir' }))
    fireEvent.click(screen.getByRole('button', { name: 'Substituída' }))

    expect(screen.getByText('Sem elegíveis para este slot. Registe como GAP.')).toBeInTheDocument()
  })

  it('bloqueia ações operacionais para role professor', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'prof@escola.pt',
        role: 'teacher',
        teacherId: 10,
        orgId: 1,
      },
    })

    schoolHooks.useOccurrences.mockReturnValue({
      data: [defaultOccurrence],
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(screen.getByText('Modo de leitura: apenas admin pode confirmar decisões operacionais.')).toBeInTheDocument()

    const blockedButton = screen.getByRole('button', { name: 'Sem permissão' })
    expect(blockedButton).toBeDisabled()
  })

  it('reage a erro transacional do backend com mensagem operacional', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [defaultOccurrence],
      isLoading: false,
      isError: false,
    })

    const mutateWithConflict = vi.fn((_payload, options) => {
      options.onError({
        response: {
          data: {
            detail: 'Conflito de concorrência: ocorrência já foi decidida.',
          },
        },
      })
    })

    schoolHooks.useUpdateOccurrence.mockReturnValue({
      mutate: mutateWithConflict,
      isPending: false,
      isError: false,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Decidir' }))
    fireEvent.click(screen.getByLabelText('Confirmo esta decisão operacional para a ocorrência selecionada.'))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar decisão' }))

    expect(screen.getByText('Conflito de concorrência: ocorrência já foi decidida.')).toBeInTheDocument()
  })

  it('mostra top 3 recomendações por defeito e permite expandir lista completa', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [defaultOccurrence],
      isLoading: false,
      isError: false,
    })

    schoolHooks.useSubstituteRecommendations.mockReturnValue({
      data: [
        {
          rank: 1,
          teacher_id: 11,
          teacher_name: 'Prof. Bruno',
          subject_id: 200,
          subject_name: 'Português',
          substitutions_in_period: 1,
          daily_load_hours: 2,
          days_since_last_substitution: 5,
          justification: 'Ranking 1',
        },
        {
          rank: 2,
          teacher_id: 12,
          teacher_name: 'Prof. Carla',
          subject_id: 201,
          subject_name: 'Inglês',
          substitutions_in_period: 2,
          daily_load_hours: 3,
          days_since_last_substitution: 4,
          justification: 'Ranking 2',
        },
        {
          rank: 3,
          teacher_id: 13,
          teacher_name: 'Prof. Diana',
          subject_id: 202,
          subject_name: 'Matemática',
          substitutions_in_period: 3,
          daily_load_hours: 4,
          days_since_last_substitution: 3,
          justification: 'Ranking 3',
        },
        {
          rank: 4,
          teacher_id: 14,
          teacher_name: 'Prof. Eduardo',
          subject_id: 203,
          subject_name: 'TIC',
          substitutions_in_period: 4,
          daily_load_hours: 5,
          days_since_last_substitution: 2,
          justification: 'Ranking 4',
        },
      ],
      isLoading: false,
      isError: false,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Decidir' }))
    fireEvent.click(screen.getByRole('button', { name: 'Substituída' }))

    expect(screen.queryByText(/#4 Prof\. Eduardo — TIC/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ver lista completa' }))

    expect(screen.getByText(/#4 Prof\. Eduardo — TIC/)).toBeInTheDocument()
  })

  it('mantém ocorrências fechadas em modo somente leitura', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [{
        ...defaultOccurrence,
        id: 303,
        status: 'GAP',
        decided_by_user_id: 99,
        decided_at: '2026-04-11T08:00:00Z',
      }],
      isLoading: false,
      isError: false,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Resolvidas \(1\)/i }))
    const closedButton = screen.getByRole('button', { name: 'Fechada' })
    expect(closedButton).toBeDisabled()
  })

  it('aplica ordenação determinística por data e id', () => {
    schoolHooks.useOccurrences.mockReturnValue({
      data: [
        {
          ...defaultOccurrence,
          id: 200,
          date: '2026-04-10',
          planned_teacher_id: 11,
          executed_teacher_id: 11,
        },
        {
          ...defaultOccurrence,
          id: 100,
          date: '2026-04-10',
          planned_teacher_id: 10,
          executed_teacher_id: 10,
        },
        {
          ...defaultOccurrence,
          id: 300,
          date: '2026-04-12',
          planned_teacher_id: 10,
          executed_teacher_id: 10,
        },
      ],
      isLoading: false,
      isError: false,
    })

    renderPage()

    const dataRows = screen.getAllByRole('row').slice(1)
    const orderedDates = dataRows.map((row) => row.querySelector('td:nth-child(1)')?.textContent?.trim())
    const orderedTeachers = dataRows.map((row) => row.querySelector('td:nth-child(5)')?.textContent?.trim())

    expect(orderedDates).toEqual(['10/04/2026', '10/04/2026', '12/04/2026'])
    expect(orderedTeachers).toEqual(['Prof. Ana', 'Prof. Bruno', 'Prof. Ana'])
  })
})
