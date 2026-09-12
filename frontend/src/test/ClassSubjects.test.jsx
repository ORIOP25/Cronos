import { renderWithRouter } from './testUtils'
import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import ClassSubjects from '../pages/ClassSubjects'

const { useClassSubjectsMock, mutationMock } = vi.hoisted(() => ({
  useClassSubjectsMock: vi.fn(),
  mutationMock: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  }),
}))

vi.mock('../features/catalog/data', () => ({
  useClassSubjects: () => useClassSubjectsMock(),
  useAvailableSubjects: () => ({ data: [], isLoading: false }),
  useEligibleTeachers: () => ({
    data: [{ id: 5, name: 'Ana Silva', current_classes_count: 0 }],
    isLoading: false,
  }),
  useAddClassSubject: mutationMock,
  useUpdateClassSubjectTeacher: mutationMock,
  useRemoveClassSubject: mutationMock,
}))

describe('ClassSubjects', () => {
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
