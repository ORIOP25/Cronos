import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import ClassDetails from '../pages/ClassDetails'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({
  classDetails: vi.fn(),
  classSubjects: vi.fn(),
  updateClass: vi.fn(),
  updateProgress: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useClassDetails: (classId) => hooks.classDetails(classId),
  useClassSubjects: (classId) => hooks.classSubjects(classId),
  useUpdateCourseClass: () => hooks.updateClass(),
  useUpdateClassProgress: () => hooks.updateProgress(),
}))

const createMutationState = () => ({
  error: null,
  isError: false,
  isPending: false,
  mutate: vi.fn(),
  reset: vi.fn(),
})

const createClassData = ({ subjects } = {}) => ({
  name: '10.º A',
  size: 24,
  start_year: 2025,
  end_year: 2028,
  grade_level: 10,
  course: {
    name: 'Técnico de Informática',
    abbreviation: 'TIS',
  },
  subjects: subjects ?? [
    {
      id: 2,
      name: 'Zeta',
      required_room_type: 'normal',
      total_hours: 50,
      completed_hours: 25,
      overall_percentage: 50,
      modules: [
        { id: 22, code: 'M2', name: 'Módulo 2', hours_total: 25, hours_completed: 25, is_completed: true, order: 2 },
        { id: 21, code: 'M1', name: 'Módulo 1', hours_total: 25, hours_completed: 0, is_completed: false, order: 1 },
      ],
    },
    {
      id: 1,
      name: 'Algoritmos',
      required_room_type: 'lab',
      total_hours: 10,
      completed_hours: 0,
      overall_percentage: 0,
      modules: [
        { id: 11, code: 'A1', name: 'Introdução', hours_total: 10, hours_completed: 0, is_completed: false, order: 1 },
      ],
    },
  ],
})

const renderClassDetails = () => renderWithRouter(
  <Routes>
    <Route path="/courses/:courseId/classes/:classId" element={<ClassDetails />} />
  </Routes>,
  { initialEntries: ['/courses/7/classes/11'] },
)

describe('ClassDetails composition', () => {
  beforeEach(() => {
    hooks.classDetails.mockReset().mockReturnValue({
      data: createClassData(),
      isLoading: false,
      error: null,
    })
    hooks.classSubjects.mockReset().mockReturnValue({
      data: {
        subjects: [
          { id: 1, subject_name: 'Algoritmos', teacher_id: null, teacher_name: null, modules: [{ id: 11, selected: true }, { id: 12, selected: false }] },
          { id: 2, subject_name: 'Zeta', teacher_id: 5, teacher_name: 'Ana Silva', modules: [{ id: 21, selected: true }] },
        ],
      },
    })
    hooks.updateClass.mockReset().mockReturnValue(createMutationState())
    hooks.updateProgress.mockReset().mockReturnValue(createMutationState())
  })

  it('orders the page and keeps global progress inside the discipline section', () => {
    renderClassDetails()

    const header = screen.getByRole('heading', { name: '10.º A' }).closest('.card')
    const subjectsTitle = screen.getByText('Disciplinas & Professores')
    const progressTitle = screen.getByText('Progresso por Disciplina')
    const subjectsHeader = subjectsTitle.closest('.card-header')
    const progressHeader = progressTitle.closest('.card-header')
    const progressCard = progressTitle.closest('.card')

    expect(header).toHaveTextContent('Técnico de Informática')
    expect(header).toHaveTextContent('2025/2028')
    expect(header).toHaveTextContent('10.º ano')
    expect(header).toHaveTextContent('24 alunos')
    expect(header).not.toHaveTextContent('25/60h')
    expect(header).not.toHaveTextContent('1/3 módulos')

    expect(header.compareDocumentPosition(subjectsTitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(subjectsTitle.compareDocumentPosition(progressTitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(subjectsHeader.querySelector('.badge')).toBeNull()
    expect(progressHeader.querySelector('.badge')).toBeNull()

    expect(progressCard).toHaveTextContent('Progresso Global')
    expect(progressCard).toHaveTextContent('25 de 60 horas · 1 de 3 módulos concluídos')
    expect(progressCard).toHaveTextContent('42%')
    expect(within(progressCard).getByRole('progressbar', { name: 'Progresso global da turma' })).toHaveAttribute('aria-valuenow', '42')
    expect(progressCard).toHaveTextContent('25/50h')
    expect(progressCard).toHaveTextContent('Módulo 1')
    expect(screen.getByText('Sem professor')).toBeInTheDocument()
  })

  it('saves the header with the course and class from the route', () => {
    const mutation = createMutationState()
    hooks.updateClass.mockReturnValue(mutation)
    renderClassDetails()

    fireEvent.click(screen.getByTitle('Editar nome e capacidade'))
    fireEvent.change(screen.getByLabelText('Nome da Turma'), { target: { value: ' 10.º B ' } })
    fireEvent.change(screen.getByLabelText('Capacidade (alunos)'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(mutation.mutate).toHaveBeenCalledWith({
      courseId: 7,
      classId: 11,
      data: { name: '10.º B', size: 25 },
    }, expect.any(Object))
  })

  it('does not mutate the React Query subject order while rendering', () => {
    const classData = createClassData()
    hooks.classDetails.mockReturnValue({ data: classData, isLoading: false, error: null })

    renderClassDetails()

    expect(classData.subjects.map(subject => subject.name)).toEqual(['Zeta', 'Algoritmos'])
    expect(classData.subjects[0].modules.map(module => module.name)).toEqual(['Módulo 2', 'Módulo 1'])
    expect(screen.getAllByText('Algoritmos').length).toBeGreaterThan(0)
  })

  it('shows zero-valued global progress when a discipline exists', () => {
    hooks.classDetails.mockReturnValue({
      data: createClassData({
        subjects: [{
          id: 9,
          name: 'Sem módulos',
          required_room_type: 'normal',
          total_hours: 0,
          completed_hours: 0,
          overall_percentage: 0,
          modules: [],
        }],
      }),
      isLoading: false,
      error: null,
    })

    renderClassDetails()

    const progressCard = screen.getByText('Progresso por Disciplina').closest('.card')
    expect(progressCard).toHaveTextContent('0 de 0 horas · 0 de 0 módulos concluídos')
    expect(progressCard).toHaveTextContent('0%')
    expect(within(progressCard).getByRole('progressbar', { name: 'Progresso global da turma' })).toHaveAttribute('aria-valuenow', '0')
  })

  it('shows only the empty state when the class has no disciplines', () => {
    hooks.classDetails.mockReturnValue({
      data: createClassData({ subjects: [] }),
      isLoading: false,
      error: null,
    })

    renderClassDetails()

    const progressCard = screen.getByText('Progresso por Disciplina').closest('.card')
    expect(screen.getByText('Nenhuma disciplina associada ao curso desta turma.')).toBeInTheDocument()
    expect(progressCard).not.toHaveTextContent('Progresso Global')
    expect(within(progressCard).queryByRole('progressbar', { name: 'Progresso global da turma' })).not.toBeInTheDocument()
  })

  it('shows the selected module count per discipline in the subjects table', () => {
    renderClassDetails()

    const table = screen.getByText('Disciplinas & Professores').closest('.card')
    expect(within(table).getByRole('columnheader', { name: 'Módulos' })).toBeInTheDocument()
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getByText('1/2')).toBeInTheDocument()
    expect(within(rows[2]).getByText('1/1')).toBeInTheDocument()
  })

  it('shows the empty message when a discipline has no selected modules', () => {
    hooks.classDetails.mockReturnValue({
      data: createClassData({
        subjects: [{
          id: 9,
          name: 'Sem módulos',
          required_room_type: 'normal',
          total_hours: 0,
          completed_hours: 0,
          overall_percentage: 0,
          modules: [],
        }],
      }),
      isLoading: false,
      error: null,
    })

    renderClassDetails()

    const progressCard = screen.getByText('Progresso por Disciplina').closest('.card')
    expect(within(progressCard).getByText('Nenhum módulo selecionado para esta turma.')).toBeInTheDocument()
  })
})
