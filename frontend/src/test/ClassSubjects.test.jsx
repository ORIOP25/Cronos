import { renderWithRouter } from './testUtils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import ClassSubjects from '../pages/ClassSubjects'

const {
  useClassSubjectsMock,
  mutationMock,
  updateClassSubjectMock,
  eligibleTeachersMock,
  jointCandidatesMock,
  createJointMock,
  updateJointMock,
  deleteJointMock,
} = vi.hoisted(() => ({
  useClassSubjectsMock: vi.fn(),
  mutationMock: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  }),
  updateClassSubjectMock: vi.fn(),
  eligibleTeachersMock: vi.fn(),
  jointCandidatesMock: vi.fn(),
  createJointMock: vi.fn(),
  updateJointMock: vi.fn(),
  deleteJointMock: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useClassSubjects: () => useClassSubjectsMock(),
  useAvailableSubjects: () => ({ data: [], isLoading: false }),
  useEligibleTeachers: () => eligibleTeachersMock(),
  useAddClassSubject: mutationMock,
  useUpdateClassSubject: () => updateClassSubjectMock(),
  useRemoveClassSubject: mutationMock,
  useJointCandidates: (...args) => jointCandidatesMock(...args),
  useCreateJointGroup: () => createJointMock(),
  useUpdateJointGroup: () => updateJointMock(),
  useDeleteJointGroup: () => deleteJointMock(),
}))

const baseSubjects = {
  data: {
    class_name: 'TEE 26/29',
    course_name: 'Técnico de Eletrónica',
    grade_level: 10,
    subjects: [
      {
        id: 1, subject_id: 1, subject_name: 'Português', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: 5, teacher_name: 'Ana Silva',
        modules: [
          { id: 11, name: 'Módulo 1', code: 'M1', hours_total: 25, order: 1, selected: true },
          { id: 12, name: 'Módulo 2', code: null, hours_total: 30, order: 2, selected: false },
        ],
      },
      {
        id: 2, subject_id: 2, subject_name: 'Programação', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: 5, teacher_name: 'Ana Silva',
        modules: [
          { id: 21, name: 'Módulo A', code: 'A', hours_total: 50, order: 1, selected: true },
        ],
      },
    ],
  },
  error: null,
  isLoading: false,
}

const subjectsWithModules = {
  data: {
    class_name: 'TEE 26/29',
    course_name: 'Técnico de Eletrónica',
    grade_level: 10,
    subjects: [
      {
        id: 1,
        subject_id: 1,
        subject_name: 'Português',
        room_type: { id: 1, name: 'Normal', is_normal: true },
        teacher_id: 5,
        teacher_name: 'Ana Silva',
        modules: [
          { id: 11, name: 'Módulo 1', code: 'M1', hours_total: 25, order: 0, selected: true },
          { id: 12, name: 'Módulo 2', code: 'M2', hours_total: 30, order: 1, selected: true },
          { id: 13, name: 'Módulo 3', code: 'M3', hours_total: 20, order: 2, selected: false },
        ],
      },
      {
        id: 2,
        subject_id: 2,
        subject_name: 'Programação',
        room_type: { id: 1, name: 'Normal', is_normal: true },
        teacher_id: null,
        teacher_name: null,
        modules: [
          { id: 21, name: 'Fundamentos', code: 'P1', hours_total: 40, order: 0, selected: false },
        ],
      },
    ],
  },
  error: null,
  isLoading: false,
}

const subjectsWithJoint = {
  data: {
    class_name: 'TEE 26/29',
    course_name: 'Técnico de Eletrónica',
    grade_level: 10,
    subjects: [
      {
        id: 1,
        subject_id: 1,
        subject_name: 'Português',
        room_type: { id: 1, name: 'Normal', is_normal: true },
        teacher_id: 5,
        teacher_name: 'Ana Silva',
        modules: [
          { id: 11, name: 'Módulo 1', code: 'M1', hours_total: 25, order: 0, selected: true },
          { id: 12, name: 'Módulo 2', code: 'M2', hours_total: 30, order: 1, selected: true },
          { id: 13, name: 'Módulo 3', code: 'M3', hours_total: 20, order: 2, selected: false },
        ],
        joint_group: {
          id: 3,
          subject_id: 1,
          subject_name: 'Português',
          teacher_id: 5,
          module_ids: [11, 12],
          classes: [
            { class_id: 11, class_name: '10.º MKT', course_abbreviation: 'MKT', grade_level: 10 },
            { class_id: 12, class_name: '10.º MAS', course_abbreviation: 'MAS', grade_level: 10 },
          ],
        },
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
    eligibleTeachersMock.mockReset()
    eligibleTeachersMock.mockReturnValue({
      data: [{ id: 5, name: 'Ana Silva', current_classes_count: 0 }],
      isLoading: false,
    })
    jointCandidatesMock.mockReset()
    jointCandidatesMock.mockReturnValue({ data: [], isLoading: false })
    createJointMock.mockReset()
    createJointMock.mockReturnValue(mutationMock())
    updateJointMock.mockReset()
    updateJointMock.mockReturnValue(mutationMock())
    deleteJointMock.mockReset()
    deleteJointMock.mockReturnValue(mutationMock())
  })

  it('groups compact subject rows without hiding assignment or module controls', () => {
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)
    const list = screen.getByRole('list', { name: 'Disciplinas da turma' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByRole('combobox', { name: 'Professor de Português' })).toBeEnabled()
    expect(within(rows[0]).getByRole('button', { name: 'Remover Português' })).toBeEnabled()
    const modules = within(rows[0]).getByRole('button', { name: 'Módulos: 1 de 2 · 25 h' })
    expect(modules).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(modules)
    expect(within(rows[0]).getByRole('checkbox', { name: 'M1 Módulo 1 · 25 h' })).toBeChecked()
    expect(within(rows[0]).getByRole('button', { name: 'Dar em conjunto com…' })).toBeEnabled()
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

    expect(screen.getAllByText('Normal').length).toBeGreaterThan(0)
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
          { id: 1, subject_id: 1, subject_name: 'Português', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: 5, teacher_name: 'Ana Silva' },
          { id: 2, subject_id: 2, subject_name: 'Programação', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: 5, teacher_name: 'Ana Silva' },
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
    expect(container.querySelectorAll('.compact-row > .row > .col-md-2')).toHaveLength(2)

    unmount()
    const readOnlyRender = renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" readOnly />)
    expect(screen.queryByRole('button', { name: 'Remover Português' })).not.toBeInTheDocument()
    expect(readOnlyRender.container.querySelectorAll('.compact-row > .row > .col-md-2')).toHaveLength(0)
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
            id: 1, subject_id: 1, subject_name: 'Português', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: 5, teacher_name: 'Ana Silva',
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
          { id: 1, subject_id: 1, subject_name: 'Português', room_type: { id: 1, name: 'Normal', is_normal: true }, teacher_id: null, teacher_name: null, modules: [] },
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

  it('shows the joint summary and locks joint modules in the checklist', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    expect(screen.getByText(/Em conjunto com 10\.º MAS/)).toBeInTheDocument()
    expect(screen.getByText(/Módulos M1, M2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Desfazer' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Módulos: 2 de 3 · 55 h' }))
    expect(screen.getByLabelText('M1 Módulo 1 · 25 h')).toBeDisabled()
    expect(screen.getAllByText('Retire primeiro este módulo da aula conjunta.').length).toBeGreaterThan(0)
  })

  it('offers to create a joint group when the subject has none', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithModules)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    expect(screen.getAllByRole('button', { name: /Dar em conjunto com/ }).length).toBeGreaterThan(0)
  })

  it('marks only the common modules and disables a started module in the joint modal', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithModules)
    jointCandidatesMock.mockReturnValue({
      data: [{
        class_id: 12,
        class_name: '10.º MAS',
        course_abbreviation: 'MAS',
        grade_level: 10,
        teacher_id: 5,
        selected_module_ids: [11, 12, 13],
        started_module_ids: [12],
      }],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getAllByRole('button', { name: /Dar em conjunto com/ })[0])
    expect(screen.getByText('Aula conjunta · Português')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/10\.º MAS/))

    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText('M1 Módulo 1 · 25 h')).toBeChecked()
    expect(dialog.getByLabelText('M2 Módulo 2 · 30 h')).not.toBeChecked()
    expect(dialog.getByLabelText('M2 Módulo 2 · 30 h')).toBeDisabled()
    expect(screen.getByText('Já começou')).toBeInTheDocument()
  })

  it('renders the other edit members and never unions an invalid group module into common', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    jointCandidatesMock.mockReturnValue({
      data: [
        { class_id: 11, name: '10.º MKT', selected_module_ids: [11, 12], started_module_ids: [] },
        { class_id: 12, name: '10.º MAS', selected_module_ids: [11], started_module_ids: [] },
      ],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))

    expect(jointCandidatesMock).toHaveBeenCalledWith(1, 11, 3, true)

    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText(/10\.º MAS/)).toBeChecked()
    expect(dialog.getByLabelText('M1 Módulo 1 · 25 h')).toBeChecked()
    // M2 is in joint_group.module_ids but is not common to both members.
    expect(dialog.getByLabelText('M2 Módulo 2 · 30 h')).not.toBeChecked()
    expect(dialog.getByLabelText('M2 Módulo 2 · 30 h')).toBeDisabled()
  })

  it('locks the class choice once a previous joint module began', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    jointCandidatesMock.mockReturnValue({
      data: [
        { class_id: 11, name: '10.º MKT', selected_module_ids: [11, 12], started_module_ids: [11] },
        { class_id: 12, name: '10.º MAS', selected_module_ids: [11, 12], started_module_ids: [] },
      ],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))

    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText(/10\.º MAS/)).toBeDisabled()
    expect(dialog.getByText(/Não pode juntar nem retirar turmas/)).toBeInTheDocument()
  })

  it('disables a source-started module on create and omits it from the payload', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithModules)
    const mutation = mutationMock()
    createJointMock.mockReturnValue(mutation)
    jointCandidatesMock.mockReturnValue({
      data: [
        { class_id: 11, name: '10.º MKT', selected_module_ids: [11, 12], started_module_ids: [11] },
        {
          class_id: 12,
          class_name: '10.º MAS',
          course_abbreviation: 'MAS',
          grade_level: 10,
          teacher_id: 5,
          selected_module_ids: [11, 12],
          started_module_ids: [],
        },
      ],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getAllByRole('button', { name: /Dar em conjunto com/ })[0])
    fireEvent.click(screen.getByLabelText(/10\.º MAS/))

    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText('M1 Módulo 1 · 25 h')).toBeDisabled()
    expect(dialog.getByLabelText('M1 Módulo 1 · 25 h')).not.toBeChecked()
    expect(dialog.getByLabelText('M2 Módulo 2 · 30 h')).toBeChecked()
    expect(screen.getByText('Já começou')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Criar aula conjunta' }))

    expect(jointCandidatesMock).toHaveBeenCalledWith(1, 11, undefined, true)
    expect(mutation.mutate).toHaveBeenCalledWith(
      { subjectId: 1, classIds: [11, 12], moduleIds: [12], teacherId: 5 },
      expect.any(Object),
    )
  })

  it('requires a teacher choice when the member classes have different teachers', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithModules)
    eligibleTeachersMock.mockReturnValue({
      data: [
        { id: 5, name: 'Ana Silva', current_classes_count: 0 },
        { id: 7, name: 'Rui Costa', current_classes_count: 0 },
      ],
      isLoading: false,
    })
    jointCandidatesMock.mockReturnValue({
      data: [{
        class_id: 12,
        class_name: '10.º MAS',
        course_abbreviation: 'MAS',
        grade_level: 10,
        teacher_id: 7,
        selected_module_ids: [11, 12],
        started_module_ids: [],
      }],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getAllByRole('button', { name: /Dar em conjunto com/ })[0])
    fireEvent.click(screen.getByLabelText(/10\.º MAS/))

    expect(screen.getByLabelText('Professor da aula conjunta')).toBeInTheDocument()
    expect(screen.getByText(/Esta alteração também muda 10\.º MAS/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Criar aula conjunta' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Professor da aula conjunta'), { target: { value: '7' } })
    expect(screen.getByRole('button', { name: 'Criar aula conjunta' })).toBeEnabled()
  })

  it('requires an explicit teacher when no member has an assigned teacher', () => {
    useClassSubjectsMock.mockReturnValue({
      data: {
        class_name: 'TEE 26/29',
        grade_level: 10,
        subjects: [
          {
            id: 1,
            subject_id: 1,
            subject_name: 'Português',
            room_type: { id: 1, name: 'Normal', is_normal: true },
            teacher_id: null,
            teacher_name: null,
            modules: [{ id: 11, name: 'Módulo 1', code: 'M1', hours_total: 25, order: 0, selected: true }],
          },
        ],
      },
      error: null,
      isLoading: false,
    })
    jointCandidatesMock.mockReturnValue({
      data: [{
        class_id: 12,
        class_name: '10.º MAS',
        course_abbreviation: 'MAS',
        grade_level: 10,
        teacher_id: null,
        selected_module_ids: [11],
        started_module_ids: [],
      }],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: /Dar em conjunto com/ }))
    fireEvent.click(screen.getByLabelText(/10\.º MAS/))

    expect(screen.getByLabelText('Professor da aula conjunta')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Criar aula conjunta' })).toBeDisabled()
  })

  it('shows a joint API error next to the class field', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithModules)
    const mutation = mutationMock()
    mutation.mutate = vi.fn((_payload, options) => options.onError({
      response: { status: 409, data: { detail: { code: 'JOINT_CLASS_ALREADY_JOINED' } } },
    }))
    createJointMock.mockReturnValue(mutation)
    jointCandidatesMock.mockReturnValue({
      data: [{
        class_id: 12,
        class_name: '10.º MAS',
        course_abbreviation: 'MAS',
        grade_level: 10,
        teacher_id: 5,
        selected_module_ids: [11, 12],
        started_module_ids: [],
      }],
      isLoading: false,
    })
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getAllByRole('button', { name: /Dar em conjunto com/ })[0])
    fireEvent.click(screen.getByLabelText(/10\.º MAS/))
    fireEvent.click(screen.getByRole('button', { name: 'Criar aula conjunta' }))

    const turmas = screen.getByText('Turmas').closest('fieldset')
    expect(within(turmas).getByRole('alert')).toHaveTextContent(/atualize a página/i)
  })

  it('confirms before undoing a joint group and calls the delete mutation', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    const mutation = mutationMock()
    deleteJointMock.mockReturnValue(mutation)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    expect(screen.getByText(/passam a ter Português em separado/)).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Desfazer' }))

    expect(mutation.mutate).toHaveBeenCalledWith({ groupId: 3, classIds: [11, 12] }, expect.any(Object))
  })

  it('confirms the teacher change for a joint subject', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    eligibleTeachersMock.mockReturnValue({
      data: [
        { id: 5, name: 'Ana Silva', current_classes_count: 0 },
        { id: 7, name: 'Rui Costa', current_classes_count: 0 },
      ],
      isLoading: false,
    })
    const mutation = mutationMock()
    updateClassSubjectMock.mockReturnValue(mutation)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" />)

    fireEvent.change(
      screen.getByRole('combobox', { name: 'Professor de Português' }),
      { target: { value: '7' } },
    )

    expect(screen.getByText(/O professor muda também em 10\.º MAS/)).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mudar professor' }))

    expect(mutation.mutate).toHaveBeenCalledWith(
      { classId: 11, subjectId: 1, teacherId: 7 },
      expect.any(Object),
    )
  })

  it('keeps the joint controls read-only in readOnly mode', () => {
    useClassSubjectsMock.mockReturnValue(subjectsWithJoint)
    renderWithRouter(<ClassSubjects courseIdOverride="9" classIdOverride="11" readOnly />)

    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desfazer' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dar em conjunto com/ })).not.toBeInTheDocument()
  })
})
