import { renderWithRouter } from './testUtils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import ClassSubjects from '../pages/ClassSubjects'

const { useClassSubjectsMock, mutationMock, updateClassSubjectMock } = vi.hoisted(() => ({
  useClassSubjectsMock: vi.fn(),
  mutationMock: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  }),
  updateClassSubjectMock: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useClassSubjects: () => useClassSubjectsMock(),
  useAvailableSubjects: () => ({ data: [], isLoading: false }),
  useEligibleTeachers: () => ({
    data: [{ id: 5, name: 'Ana Silva', current_classes_count: 0 }],
    isLoading: false,
  }),
  useAddClassSubject: mutationMock,
  useUpdateClassSubject: () => updateClassSubjectMock(),
  useRemoveClassSubject: mutationMock,
}))

const baseSubjects = {
  data: {
    class_name: 'TEE 26/29',
    course_name: 'Técnico de Eletrónica',
    grade_level: 10,
    subjects: [
      {
        id: 1, subject_id: 1, subject_name: 'Português', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva',
        modules: [
          { id: 11, name: 'Módulo 1', code: 'M1', hours_total: 25, order: 1, selected: true },
          { id: 12, name: 'Módulo 2', code: null, hours_total: 30, order: 2, selected: false },
        ],
      },
      {
        id: 2, subject_id: 2, subject_name: 'Programação', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva',
        modules: [
          { id: 21, name: 'Módulo A', code: 'A', hours_total: 50, order: 1, selected: true },
        ],
      },
    ],
  },
  error: null,
  isLoading: false,
}

describe('ClassSubjects', () => {
  beforeEach(() => {
    useClassSubjectsMock.mockReturnValue(baseSubjects)
    updateClassSubjectMock.mockReset()
    updateClassSubjectMock.mockReturnValue(mutationMock())
  })

  it('keeps a competency block beside the assignment without a toast', async () => {
    const error = {
      response: { status: 422, data: { detail: { code: 'teacher_competency_missing' } } },
    }
    updateClassSubjectMock.mockReturnValue({
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
    updateClassSubjectMock.mockReturnValue({
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

  it('shows the module summary and expands a labelled checklist', () => {
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    const toggle = screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveAttribute('aria-controls', 'class-subject-modules-1')

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    const panel = document.getElementById('class-subject-modules-1')
    expect(panel).toBeInTheDocument()
    expect(within(panel).getByRole('checkbox', { name: 'M1 Módulo 1 · 25 h' })).toBeChecked()
    expect(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' })).not.toBeChecked()
  })

  it('sends the full module list when a module is selected', () => {
    const mutation = mutationMock()
    updateClassSubjectMock.mockReturnValue(mutation)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' }))

    expect(mutation.mutate).toHaveBeenCalledWith(
      { classId: 11, subjectId: 1, moduleIds: [11, 12] },
      expect.any(Object),
    )
  })

  it('disables the row module controls while a save is pending', () => {
    updateClassSubjectMock.mockReturnValue({ ...mutationMock(), isPending: true })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    expect(within(panel).getByRole('checkbox', { name: 'M1 Módulo 1 · 25 h' })).toBeDisabled()
    expect(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Professor de Português' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Remover Português' })).toBeDisabled()
  })

  it('shows a single fixed-id success toast after saving modules', async () => {
    const mutation = { ...mutationMock(), mutate: (_payload, options) => options.onSuccess() }
    updateClassSubjectMock.mockReturnValue(mutation)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    const checkbox = within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' })
    fireEvent.click(checkbox)
    fireEvent.click(checkbox)

    const toaster = document.querySelector('[data-rht-toaster]')
    expect(await within(toaster).findAllByText('Módulos atualizados.')).toHaveLength(1)
  })

  it('reports a transient module failure as a toast', async () => {
    const error = { response: { status: 503, data: { detail: { code: 'service_unavailable' } } } }
    updateClassSubjectMock.mockReturnValue({
      ...mutationMock(),
      mutate: (_payload, options) => options.onError(error),
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' }))

    const toaster = document.querySelector('[data-rht-toaster]')
    expect(await within(toaster).findByText(/tente novamente dentro de instantes/i)).toBeInTheDocument()
    expect(document.getElementById('class-subject-modules-error-1')).not.toBeInTheDocument()
  })

  it('keeps a module business block beside the list without a toast', async () => {
    const error = { response: { status: 400, data: { detail: { code: 'bad_request' } } } }
    updateClassSubjectMock.mockReturnValue({
      ...mutationMock(),
      mutate: (_payload, options) => options.onError(error),
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/não foi possível concluir/i)
    expect(document.querySelector('[data-rht-toaster]')).toBeEmptyDOMElement()
  })

  it('does not change the module summary after a failed save', () => {
    const error = { response: { status: 400, data: { detail: { code: 'bad_request' } } } }
    const mutate = vi.fn((_payload, options) => options.onError(error))
    updateClassSubjectMock.mockReturnValue({ ...mutationMock(), mutate })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Módulo 2 · 30 h' }))

    expect(mutate).toHaveBeenCalledWith(
      { classId: 11, subjectId: 1, moduleIds: [11, 12] },
      expect.any(Object),
    )
    expect(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' })).toBeInTheDocument()
  })

  it('flags subjects without selected modules and counts them in the header', () => {
    useClassSubjectsMock.mockReturnValue({
      data: {
        class_name: 'TEE 26/29',
        course_name: 'Técnico de Eletrónica',
        grade_level: 10,
        subjects: [
          {
            id: 1, subject_id: 1, subject_name: 'Português', required_room_type: 'normal', teacher_id: 5, teacher_name: 'Ana Silva',
            modules: [{ id: 11, name: 'M1', code: 'M1', hours_total: 25, order: 1, selected: false }],
          },
        ],
      },
      error: null,
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    expect(screen.getByText('Sem módulos', { selector: 'span.text-warning' })).toBeInTheDocument()
    expect(screen.getByTitle('Sem módulos')).toBeInTheDocument()
    expect(screen.getByText('1 sem módulos')).toBeInTheDocument()
  })

  it('explains when a subject has no catalogue modules', () => {
    useClassSubjectsMock.mockReturnValue({
      data: {
        class_name: 'TEE 26/29',
        course_name: 'Técnico de Eletrónica',
        grade_level: 10,
        subjects: [
          { id: 1, subject_id: 1, subject_name: 'Português', required_room_type: 'normal', teacher_id: null, teacher_name: null, modules: [] },
        ],
      },
      error: null,
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 0 de 0 · 0 h' }))
    expect(screen.getByText('Esta disciplina não tem módulos. Adicione-os em Disciplinas.')).toBeInTheDocument()
  })

  it('keeps the module checklist read-only when readOnly', () => {
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" readOnly />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    expect(within(panel).getByRole('checkbox', { name: 'M1 Módulo 1 · 25 h' })).toBeDisabled()
  })

  it('keeps the module checklist read-only inside the tutorial', () => {
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" allowedActions={[]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' }))
    const panel = document.getElementById('class-subject-modules-1')
    expect(within(panel).getByRole('checkbox', { name: 'M1 Módulo 1 · 25 h' })).toBeDisabled()
  })
})
