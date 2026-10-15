import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Occurrences from '../pages/Occurrences'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({
  debts: vi.fn(),
  occurrences: vi.fn(),
  cancel: vi.fn(),
  update: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useCancelOccurrence: () => ({ isPending: false, mutate: hooks.cancel }),
  useDebts: (filters) => hooks.debts(filters),
  useOccurrences: (filters) => hooks.occurrences(filters),
  useSubstituteDiagnostics: () => ({ data: { candidates: [], setup_actions: [] } }),
  useSubstituteRecommendations: () => ({
    data: [{ rank: 1, teacher_id: 2, teacher_name: 'Prof.ª Maria Santos', subject_id: 2, subject_name: 'Matemática' }],
  }),
  useUpdateOccurrence: () => ({ isPending: false, mutate: hooks.update }),
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
    hooks.cancel.mockReset()
    hooks.update.mockReset()
    hooks.debts.mockReset().mockReturnValue({ data: { items: [] }, isLoading: false, isError: false })
    hooks.occurrences.mockReset().mockReturnValue({ data: { items: [] }, isLoading: false, isError: false })
  })

  it.each(['scheduler_v1', 'admin'])('reconciles only supported revoked occurrences (%s)', async (creationSource) => {
    hooks.occurrences.mockReturnValue({
      data: { items: [{ id: 1, date: '2026-10-12', status: 'REVOKED',
        operational_state: 'REVOKED', version: 5, class_name: 'TAS 10', creation_source: creationSource }] },
      isLoading: false, isError: false,
    })
    renderWithRouter(<Occurrences />, { initialEntries: ['/absences?tab=historical'] })
    if (creationSource !== 'scheduler_v1') {
      expect(screen.queryByRole('button', { name: 'Reconciliar dívida' })).not.toBeInTheDocument()
      return
    }
    fireEvent.click(await screen.findByRole('button', { name: 'Reconciliar dívida' }))
    expect(screen.getByText(/preserva.*histórico.*corrige.*dívida residual/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reconciliar', exact: true }))
    expect(hooks.cancel).toHaveBeenCalledWith({ id: 1, version: 5,
      cancelCompletedSubstituteLog: false }, expect.any(Object))
  })

  it('disables Given for a future occurrence without blocking other decisions', async () => {
    hooks.occurrences.mockReturnValue({
      data: { items: [{ id: 19, date: '2099-10-19', ends_at: '2099-10-19T09:50:00Z',
        status: 'GAP', operational_state: 'OPEN_PENDING', version: 1 }] },
      isLoading: false, isError: false,
    })
    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })
    fireEvent.click(await screen.findByRole('button', { name: 'Decidir' }))
    expect(screen.getByRole('button', { name: 'Dada' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Furo' })).toBeEnabled()
    expect(screen.getByText(/Só pode decidir.*Dada.*término/i)).toBeInTheDocument()
  })

  it('keeps the debt amount and teacher readable in mobile cards', () => {
    hooks.debts.mockReturnValue({ data: { total_gaps: 1, total_hours_owed: 50 / 60,
      items: [{ class_id: 3, subject_id: 1, class_name: 'TCONT 10', subject_name: 'Fiscalidade',
        teacher_name: 'Prof. QA', gap_occurrences: 1, hours_owed: 50 / 60 }] },
      isLoading: false, isError: false })
    renderWithRouter(<Occurrences />, { initialEntries: ['/absences?tab=debts'] })
    const cards = screen.getByRole('region', { name: 'Dívidas por turma' })
    expect(within(cards).getByText('50 min')).toBeInTheDocument()
    expect(within(cards).getByText('Prof. QA')).toBeInTheDocument()
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
      expect(screen.getAllByText('Horas em dívida').length).toBeGreaterThan(0)
      expect(screen.getByRole('cell', { name: '2 h' })).toBeInTheDocument()
    })
  })

  it('groups a joint lesson and decides each class with its own row id and version', async () => {
    hooks.occurrences.mockReturnValue({
      data: {
        items: [{
          id: 101,
          date: '2026-10-12',
          subject_name: 'Português',
          status: 'GAP',
          operational_state: 'OPEN_PENDING',
          version: 2,
          joint_lesson: {
            classes: [
              { class_id: 11, class_name: '10.º MKT', id: 101, status: 'GAP', operational_state: 'OPEN_PENDING', version: 2 },
              { class_id: 12, class_name: '10.º MAS', id: 102, status: 'OCCURRENCE', operational_state: 'OPEN_PENDING', version: 1 },
            ],
          },
        }],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })

    expect(await screen.findByText(/Aula conjunta · Português · 10\.º MKT, 10\.º MAS/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Decidir para todas' })).toBeInTheDocument()

    // Deciding the representative class bumps its revision; the sibling must
    // still be decided with its own row id and version (no false STALE 409).
    fireEvent.click(screen.getByRole('button', { name: 'Furo 10.º MKT' }))
    expect(hooks.update).toHaveBeenNthCalledWith(
      1,
      { id: 101, status: 'GAP', version: 2, classIds: [11] },
      expect.any(Object),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Furo 10.º MAS' }))
    expect(hooks.update).toHaveBeenNthCalledWith(
      2,
      { id: 102, status: 'GAP', version: 1, classIds: [12] },
      expect.any(Object),
    )
  })

  it('falls back to the card row consistently when a class has no own id', async () => {
    hooks.occurrences.mockReturnValue({
      data: {
        items: [{
          id: 30,
          date: '2026-10-12',
          subject_name: 'Português',
          status: 'GAP',
          operational_state: 'OPEN_PENDING',
          version: 5,
          joint_lesson: {
            classes: [
              { class_id: 11, class_name: '10.º MKT', operational_state: 'OPEN_PENDING' },
              { class_id: 12, class_name: '10.º MAS', operational_state: 'OPEN_PENDING' },
            ],
          },
        }],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })

    fireEvent.click(await screen.findByRole('button', { name: 'Furo 10.º MAS' }))

    expect(hooks.update).toHaveBeenCalledWith(
      { id: 30, status: 'GAP', version: 5, classIds: [12] },
      expect.any(Object),
    )
  })

  it('decides all joint classes from the modal with the representative row version', async () => {
    hooks.occurrences.mockReturnValue({
      data: {
        items: [{
          id: 101,
          date: '2026-10-12',
          subject_name: 'Português',
          status: 'GAP',
          operational_state: 'OPEN_PENDING',
          version: 2,
          joint_lesson: {
            classes: [
              { class_id: 11, class_name: '10.º MKT', id: 101, operational_state: 'OPEN_PENDING', version: 2 },
              { class_id: 12, class_name: '10.º MAS', id: 102, operational_state: 'OPEN_PENDING', version: 1 },
            ],
          },
        }],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRouter(<Occurrences />, { initialEntries: ['/absences'] })

    fireEvent.click(await screen.findByRole('button', { name: 'Decidir para todas' }))
    fireEvent.click(screen.getByLabelText(/confirmo esta decisão operacional/i))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar decisão' }))

    expect(hooks.update).toHaveBeenCalledWith(
      expect.objectContaining({ id: 101, status: 'GAP', version: 2, classIds: [11, 12] }),
      expect.any(Object),
    )
  })
})
