import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Occurrences from '../pages/Occurrences'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({
  debts: vi.fn(),
  occurrences: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useCancelOccurrence: () => ({ isPending: false, mutate: vi.fn() }),
  useDebts: (filters) => hooks.debts(filters),
  useOccurrences: (filters) => hooks.occurrences(filters),
  useSubstituteRecommendations: () => ({
    data: [{ rank: 1, teacher_id: 2, teacher_name: 'Prof.ª Maria Santos', subject_id: 2, subject_name: 'Matemática' }],
  }),
  useUpdateOccurrence: () => ({ isPending: false, mutate: vi.fn() }),
}))

vi.mock('../features/catalog/data', () => ({
  useClasses: () => ({ data: [{ id: 3, name: '10.º A' }] }),
  useSubjects: () => ({ data: [{ id: 1, name: 'Programação' }, { id: 2, name: 'Matemática' }] }),
}))

vi.mock('../features/members/data', () => ({
  useTeachers: () => ({ data: [{ id: 1, name: 'Prof. António Silva' }, { id: 2, name: 'Prof.ª Maria Santos' }] }),
}))

describe('Occurrences active tab ownership', () => {
  beforeEach(() => {
    hooks.debts.mockReset().mockReturnValue({ data: { items: [] }, isLoading: false, isError: false })
    hooks.occurrences.mockReset().mockReturnValue({ data: { items: [] }, isLoading: false, isError: false })
  })

  it('mounts only the data hook for the active tab', async () => {
    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })

    expect(hooks.occurrences).toHaveBeenCalledWith(expect.objectContaining({ status: 'OPEN_PENDING' }))
    expect(hooks.debts).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('tab', { name: /dívidas de horas/i }))

    await waitFor(() => expect(hooks.debts).toHaveBeenCalledOnce())
  })

  it('derives tab and filters from a deep link and falls back for invalid tabs', () => {
    const first = renderWithRouter(<Occurrences />, {
      initialEntries: ['/absences?tab=debts&class_id=3'],
    })

    expect(hooks.debts).toHaveBeenCalledWith({ classId: '3' })
    expect(hooks.occurrences).not.toHaveBeenCalled()
    first.unmount()

    hooks.debts.mockClear()
    hooks.occurrences.mockClear()
    renderWithRouter(<Occurrences />, { initialEntries: ['/absences?tab=invalid'] })

    expect(hooks.occurrences).toHaveBeenCalledWith(expect.objectContaining({ status: 'OPEN_PENDING' }))
    expect(hooks.debts).not.toHaveBeenCalled()
  })

  it('restricts the tutorial substitution modal to the prepared decision', async () => {
    hooks.occurrences.mockReturnValue({
      data: {
        items: [{
          id: 1,
          date: '2025-09-15',
          status: 'GAP',
          operational_state: 'OPEN_PENDING',
          planned_teacher_id: 1,
          class_name: '10.º A',
          subject_name: 'Programação',
          version: 1,
        }],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRouter(<Occurrences allowedActions={['DECIDE_SUBSTITUTION']} />, { initialEntries: ['/absences'] })
    fireEvent.click(await screen.findByRole('button', { name: 'Decidir' }))

    expect(screen.getByRole('button', { name: 'Dada' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Furo' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Substituída' })).toBeEnabled()
  })

  it('keeps tab labels as the only section headings and preserves panel content', async () => {
    hooks.occurrences.mockReturnValue({
      data: {
        items: [{
          id: 1,
          date: '2025-09-15',
          status: 'GAP',
          operational_state: 'OPEN_PENDING',
          planned_teacher_id: 1,
          class_name: '10.º A',
          subject_name: 'Programação',
          version: 1,
        }],
      },
      isLoading: false,
      isError: false,
    })
    hooks.debts.mockReturnValue({
      data: {
        total_gaps: 1,
        total_hours_owed: 2,
        items: [{
          class_id: 3,
          subject_id: 1,
          class_name: '10.º A',
          subject_name: 'Programação',
          teacher_name: 'Prof. António Silva',
          gap_occurrences: 1,
          hours_owed: 2,
        }],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })

    expect(screen.getAllByText('Decisões Pendentes')).toHaveLength(1)
    expect(screen.getByRole('columnheader', { name: 'Data/Hora' })).toBeInTheDocument()
    expect(screen.queryByText('1 pendentes')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /histórico/i }))
    await waitFor(() => {
      expect(screen.queryByText('Histórico de Ocorrências')).not.toBeInTheDocument()
      expect(screen.queryByText('1 no histórico')).not.toBeInTheDocument()
      expect(screen.getByText('Sem ocorrências no histórico com os filtros atuais.')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('tab', { name: /dívidas de horas/i }))
    await waitFor(() => {
      expect(screen.queryByText('Resumo de Dívidas de Horas')).not.toBeInTheDocument()
      expect(screen.getByText('Furos acumulados')).toBeInTheDocument()
      expect(screen.getByText('Horas em dívida')).toBeInTheDocument()
      expect(screen.getByRole('cell', { name: '2h' })).toBeInTheDocument()
    })
  })
})
