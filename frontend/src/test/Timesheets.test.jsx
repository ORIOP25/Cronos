import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Timesheets from '../pages/Timesheets'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({ timesheets: vi.fn(), week: vi.fn() }))

vi.mock('../features/operations/data', () => ({
  useTimesheets: (...args) => hooks.timesheets(...args),
  useUpdateTimesheetStatus: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../features/scheduling/data', () => ({ useWeekSchedule: (...args) => hooks.week(...args) }))
vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => ({ data: [] }),
  useWeekGridVersions: () => ({ data: null }),
}))
vi.mock('../components/WeekGrid', () => ({ default: () => <div>Grelha semanal</div> }))
vi.mock('../components/LessonLogModal', () => ({ default: () => null }))

const teachers = [
  { id: 1, teacher_id: 7, teacher_name: 'Ana', status: 'SUBMITTED', registered_slots: 3, total_slots: 4, completed_slots: 2, occurrence_slots: 1 },
  { id: 2, teacher_id: 8, teacher_name: 'Bruno', status: 'OPEN', registered_slots: 1, total_slots: 2, completed_slots: 1, occurrence_slots: 0 },
]

describe('Timesheets compact controls', () => {
  beforeEach(() => {
    hooks.timesheets.mockReset().mockReturnValue({ data: teachers, isLoading: false, isError: false })
    hooks.week.mockReset().mockReturnValue({ data: [], isLoading: false })
  })

  it('associates the status filter with its visible label and preserves server filtering', () => {
    renderWithRouter(<Timesheets initialWeekStart="2026-10-12" />)
    fireEvent.change(screen.getByLabelText('Filtrar por Estado'), { target: { value: 'SUBMITTED' } })
    expect(hooks.timesheets).toHaveBeenLastCalledWith('2026-10-12', 'SUBMITTED')
  })

  it('announces the selected teacher and keeps counts readable when changing rows', () => {
    renderWithRouter(<Timesheets initialWeekStart="2026-10-12" />)
    const ana = screen.getByRole('button', { name: /Ana/ })
    const bruno = screen.getByRole('button', { name: /Bruno/ })
    expect(ana).toHaveAttribute('aria-pressed', 'true')
    expect(ana).toHaveTextContent('3/4 registadas')
    expect(bruno).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(bruno)
    expect(bruno).toHaveAttribute('aria-pressed', 'true')
    expect(ana).toHaveAttribute('aria-pressed', 'false')
    expect(hooks.week).toHaveBeenLastCalledWith(null, 8, '2026-10-12')
  })

  it('preserves read-only management restrictions', () => {
    renderWithRouter(<Timesheets initialWeekStart="2026-10-12" readOnly />)
    expect(screen.queryByRole('button', { name: 'Aprovar', exact: true })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reabrir', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver em Horários' })).toBeEnabled()
  })

  it('shows a retry action instead of an empty grid when the week fails', async () => {
    const refetch = vi.fn()
    hooks.week.mockReturnValue({ data: [], isError: true, refetch })
    renderWithRouter(<Timesheets initialWeekStart="2026-10-12" />)
    expect(screen.getByText('Não foi possível carregar os dados da semana.')).toBeInTheDocument()
    expect(screen.queryByText('Grelha semanal')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('filters teachers by name and selects a matching teacher', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Timesheets initialWeekStart="2026-10-12" />)
    await user.type(screen.getByLabelText('Pesquisar professor'), 'bruno')
    expect(screen.queryByRole('button', { name: /Ana/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Bruno/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bruno' })).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Pesquisar professor'))
    await user.type(screen.getByLabelText('Pesquisar professor'), 'inexistente')
    expect(screen.getByText('Nenhum professor encontrado.')).toBeInTheDocument()
    expect(screen.queryByText('Grelha semanal')).not.toBeInTheDocument()
  })
})
