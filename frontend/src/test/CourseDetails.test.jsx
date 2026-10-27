import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router-dom'
import CourseDetails from '../pages/CourseDetails'
import { renderWithRouter } from './testUtils'

const { courseQuery, removeClass } = vi.hoisted(() => ({ courseQuery: vi.fn(), removeClass: vi.fn() }))
vi.mock('../features/catalog/data', () => {
  const mutation = () => ({ isPending: false, mutate: vi.fn(), reset: vi.fn() })
  return {
    useCourseDetails: () => courseQuery(),
    useUpdateCourse: mutation,
    useDeleteCourse: mutation,
    useCreateCourseClass: mutation,
    useUpdateCourseClass: mutation,
    useDeleteCourseClass: () => ({ isPending: false, mutate: removeClass }),
  }
})

const classroom = { id: 11, name: '10.º A', grade_level: 10, start_year: 2025, end_year: 2028, size: 24 }
function Location() {
  return <output data-testid="course-location">{useLocation().pathname}</output>
}
function renderCourse(props = {}) {
  return renderWithRouter(<><CourseDetails courseIdOverride={7} {...props} /><Location /></>)
}

describe('CourseDetails compact class list', () => {
  beforeEach(() => {
    removeClass.mockReset()
    courseQuery.mockReturnValue({ data: { id: 7, name: 'Informática', abbreviation: 'TGEI', classes: [classroom] }, isLoading: false })
  })

  it('shows class details and contextual actions in a compact row and keeps class navigation', () => {
    renderCourse()
    const openClass = screen.getByRole('button', { name: 'Abrir turma 10.º A' })
    const row = openClass.closest('.compact-row')
    expect(row).not.toBeNull()
    expect(row).toHaveTextContent('2025/2028')
    expect(row).toHaveTextContent('24 alunos')
    expect(within(row).getByRole('button', { name: 'Editar 10.º A' })).toHaveAttribute('data-tutorial-target', 'edit-class-11')
    expect(within(row).getByRole('button', { name: 'Remover 10.º A' })).toBeEnabled()
    fireEvent.click(openClass)
    expect(screen.getByTestId('course-location')).toHaveTextContent('/courses/7/classes/11')
  })

  it('retains the edit form and asks for confirmation before class removal', async () => {
    renderCourse()
    fireEvent.click(screen.getByRole('button', { name: 'Editar 10.º A' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Nome da Turma')).toHaveValue('10.º A')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover 10.º A' }))
    expect(removeClass).not.toHaveBeenCalled()
    const confirmation = await screen.findByRole('dialog')
    expect(confirmation).toHaveTextContent('o histórico (horários, sumários e progresso) será preservado')
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Remover', exact: true }))
    expect(removeClass).toHaveBeenCalledWith({ courseId: 7, classId: 11 }, expect.any(Object))
  })

  it('has one class creation entry point when the list is empty', () => {
    courseQuery.mockReturnValue({ data: { id: 7, name: 'Informática', abbreviation: 'TGEI', classes: [] }, isLoading: false })
    renderCourse()
    expect(screen.getAllByRole('button', { name: /Nova Turma|Criar primeira turma/ })).toHaveLength(1)
    expect(screen.getByText('Nenhuma turma criada para este curso.')).toBeInTheDocument()
  })

  it('preserves read-only and tutorial navigation restrictions', () => {
    renderCourse({ readOnly: true, navigationDisabled: true })
    expect(screen.getByRole('button', { name: 'Abrir turma 10.º A' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Editar 10.º A' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remover 10.º A' })).not.toBeInTheDocument()
  })
})
