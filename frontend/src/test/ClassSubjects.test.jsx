import { renderWithRouter } from './testUtils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import ClassSubjects from '../pages/ClassSubjects'

const { useClassSubjectsMock, mutationMock, updateTeacherMock } = vi.hoisted(() => ({
  useClassSubjectsMock: vi.fn(),
  mutationMock: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  }),
  updateTeacherMock: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useClassSubjects: () => useClassSubjectsMock(),
  useAvailableSubjects: () => ({ data: [], isLoading: false }),
  useEligibleTeachers: () => ({
    data: [{ id: 5, name: 'Ana Silva', current_classes_count: 0 }],
    isLoading: false,
  }),
  useAddClassSubject: mutationMock,
  useUpdateClassSubjectTeacher: () => updateTeacherMock(),
  useRemoveClassSubject: mutationMock,
}))

const baseSubjects = {
  data: {
    class_name: 'TEE 26/29',
    course_name: 'Técnico de Eletrónica',
    grade_level: 10,
    subjects: [
      { id: 1, subject_id: 1, subject_name: 'Português', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva' },
      { id: 2, subject_id: 2, subject_name: 'Programação', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva' },
    ],
  },
  error: null,
  isLoading: false,
}

describe('ClassSubjects', () => {
  beforeEach(() => {
    useClassSubjectsMock.mockReturnValue(baseSubjects)
    updateTeacherMock.mockReset()
    updateTeacherMock.mockReturnValue(mutationMock())
  })

  it('keeps a competency block beside the assignment without a toast', async () => {
    const error = {
      response: { status: 422, data: { detail: { code: 'teacher_competency_missing' } } },
    }
    updateTeacherMock.mockReturnValue({
      ...mutationMock(),
      mutate: (_payload, options) => options.onError(error),
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />, { withToaster: true })

    const select = screen.getByRole('combobox', { name: 'Professor de Português' })
    fireEvent.change(select, { target: { value: '5' } })

    expect(await screen.findByText(/não tem competência/i)).toBeInTheDocument()
    expect(select).toHaveAttribute('aria-invalid', 'true')
    expect(select).toHaveAttribute('aria-describedby', 'class-subject-teacher-error-1')
    expect(document.querySelector('[data-rht-toaster]')).toBeEmptyDOMElement()
  })

  it('reports a transient teacher failure as a single toast', async () => {
    const error = { response: { status: 503, data: { detail: { code: 'service_unavailable' } } } }
    updateTeacherMock.mockReturnValue({
      ...mutationMock(),
      mutate: (_payload, options) => options.onError(error),
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />, { withToaster: true })

    fireEvent.change(screen.getByRole('combobox', { name: 'Professor de Português' }), { target: { value: '5' } })

    expect(await within(document.querySelector('[data-rht-toaster]')).findByText(/tente novamente dentro de instantes/i)).toBeInTheDocument()
    expect(screen.queryByText(/não tem competência/i)).not.toBeInTheDocument()
  })

  it('keeps teachers in one column without duplicating names or the section total', () => {
    useClassSubjectsMock.mockReturnValue({
      data: {
        class_name: 'TEE 26/29',
        course_name: 'Técnico de Eletrónica',
        grade_level: 10,
        subjects: [
          { id: 1, subject_id: 1, subject_name: 'Português', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva' },
          { id: 2, subject_id: 2, subject_name: 'Programação', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva' },
        ],
      },
      error: null,
      isLoading: false,
    })

    const { container, unmount } = renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    const teacherSelects = [
      screen.getByRole('combobox', { name: 'Professor de Português' }),
      screen.getByRole('combobox', { name: 'Professor de Programação' }),
    ]
    expect(new Set(teacherSelects.map(select => select.parentElement.parentElement.className))).toEqual(new Set(['col-12 col-md-5']))
    expect(screen.getByRole('button', { name: 'Remover Português' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remover Programação' })).toBeInTheDocument()
    expect(screen.getAllByText('Ana Silva')).toHaveLength(2)

    const sectionHeader = screen.getByText('Disciplinas e Professores').closest('.card-header')
    expect(sectionHeader.querySelector('.badge')).not.toBeInTheDocument()
    expect(container.querySelector('.card-header')).toHaveTextContent('Disciplinas e Professores')
    expect(container.querySelectorAll('.card-body > .row > .col-md-2')).toHaveLength(2)

    unmount()
    const readOnlyRender = renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" readOnly />)
    expect(screen.queryByRole('button', { name: 'Remover Português' })).not.toBeInTheDocument()
    expect(readOnlyRender.container.querySelectorAll('.card-body > .row > .col-md-2')).toHaveLength(0)
  })
})
