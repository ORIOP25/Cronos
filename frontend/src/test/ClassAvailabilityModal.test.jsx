import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import ClassAvailabilityModal from '../components/ClassAvailabilityModal'
import { renderWithProviders } from './testUtils'

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  copy: vi.fn(),
  timeslots: vi.fn(),
  availability: vi.fn(),
  classes: vi.fn(),
  courses: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: (options) => mocks.timeslots(options),
  useClassAvailability: (options) => mocks.availability(options),
  useSaveClassAvailability: () => ({ mutateAsync: mocks.save, isPending: false }),
  useCopyClassAvailability: () => ({ mutateAsync: mocks.copy, isPending: false }),
  useClasses: () => mocks.classes(),
  useCourses: () => mocks.courses(),
}))

const TIMESLOTS = [
  { id: 11, day_of_week: 0, start_time: '09:00', end_time: '09:50' },
  { id: 12, day_of_week: 1, start_time: '09:00', end_time: '09:50' },
]
const COURSES = [
  { id: 1, name: 'Técnico de Informática', abbreviation: 'TIS' },
  { id: 2, name: 'Técnico de Gestão', abbreviation: 'TGEI' },
]
const CLASSES = [
  { id: 1, name: 'Zulu', course_id: 1, is_archived: false },
  { id: 2, name: 'Alfa', course_id: 1, is_archived: false },
  { id: 3, name: 'Beta', course_id: 2, is_archived: false },
  { id: 4, name: 'Arquivada', course_id: 1, is_archived: true },
]

const renderModal = (options = {}) => renderWithProviders(
  <ClassAvailabilityModal schoolClass={{ id: 9, name: '10.º A' }} onClose={vi.fn()} />,
  options,
)

const openCopyView = () => fireEvent.click(screen.getByRole('button', { name: /aplicar a outras turmas/i }))

describe('ClassAvailabilityModal', () => {
  beforeEach(() => {
    mocks.save.mockReset().mockResolvedValue({ status: 'success', count: 1 })
    mocks.copy.mockReset().mockResolvedValue({ updated_class_ids: [2, 3] })
    mocks.timeslots.mockReset().mockReturnValue({ data: TIMESLOTS, isLoading: false, error: null })
    mocks.availability.mockReset().mockReturnValue({
      data: TIMESLOTS.map((slot) => ({ timeslot_id: slot.id, score: 1 })),
      isLoading: false,
      error: null,
    })
    mocks.classes.mockReset().mockReturnValue({ data: CLASSES, isLoading: false, error: null })
    mocks.courses.mockReset().mockReturnValue({ data: COURSES, isLoading: false, error: null })
  })

  it('keeps the draft and shows a blocking error when saving fails', async () => {
    mocks.save.mockRejectedValueOnce({
      response: { status: 400, data: { detail: { code: 'bad_request', message: 'Pedido inválido.' } } },
    })
    renderModal()

    fireEvent.click(screen.getByRole('button', { name: 'Impossível' }))
    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(screen.getByText('Não foi possível concluir o pedido. Tente novamente.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /guardar disponibilidade/i })).toBeEnabled()
  })

  it('shows the class note and saves the grid, naming the class toast', async () => {
    renderModal({ withToaster: true })

    expect(screen.getByText('Disponibilidade — 10.º A')).toBeInTheDocument()
    expect(screen.getByText(/Os alunos não usam a aplicação/)).toBeInTheDocument()

    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    expect(saveButton).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Impossível' }))
    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({
      classId: 9,
      payload: [
        { timeslot_id: 11, score: -1 },
        { timeslot_id: 12, score: 1 },
      ],
    }))
    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(/Disponibilidade da turma guardada/),
    ).toBeInTheDocument()
  })

  it('blocks applying to other classes until the changes are saved', async () => {
    renderModal()

    expect(screen.getByRole('button', { name: /aplicar a outras turmas/i })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Evitar' }))
    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))

    await waitFor(() => expect(screen.getByRole('button', { name: /aplicar a outras turmas/i })).toBeDisabled())
    expect(screen.getByText('Guarde primeiro as alterações.')).toBeInTheDocument()
  })

  it('groups the target classes by course, sorts by name and omits the source', async () => {
    renderModal()
    openCopyView()

    expect(await screen.findByRole('checkbox', { name: 'Alfa' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Zulu' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Beta' })).toBeInTheDocument()
    expect(screen.getByText('TIS')).toBeInTheDocument()
    expect(screen.getByText('TGEI')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Arquivada' })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: 'Origem' })).toBeNull()
  })

  it('copies the grid to the chosen classes after confirmation', async () => {
    renderModal({ withToaster: true })
    openCopyView()

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Alfa' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Beta' }))

    const apply = screen.getByRole('button', { name: 'Aplicar a 2 turmas' })
    expect(apply).toBeEnabled()
    fireEvent.click(apply)

    expect(await screen.findByText(/Vai substituir a disponibilidade de 2 turmas pela grelha de 10.º A/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }))

    await waitFor(() => expect(mocks.copy).toHaveBeenCalledWith({ classId: 9, targetClassIds: [2, 3] }))
    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(/Disponibilidade aplicada a 2 turmas/),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /guardar disponibilidade/i })).toBeInTheDocument())
  })

  it('keeps the apply action disabled until a class is chosen', async () => {
    renderModal()
    openCopyView()

    expect(await screen.findByRole('button', { name: 'Aplicar a 0 turmas' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Voltar' })).toBeInTheDocument()
  })

  it('shows a blocking inline error when the copy is rejected', async () => {
    mocks.copy.mockRejectedValueOnce({
      response: { status: 400, data: { detail: { code: 'bad_request', message: 'Pedido inválido.' } } },
    })
    renderModal()
    openCopyView()

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Alfa' }))
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar a 1 turmas' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Aplicar' }))

    await waitFor(() => expect(screen.getByText('Não foi possível concluir o pedido. Tente novamente.')).toBeInTheDocument())
    expect(screen.getByRole('checkbox', { name: 'Alfa' })).toBeInTheDocument()
  })

  it('shows a transient toast when the copy fails temporarily', async () => {
    mocks.copy.mockRejectedValueOnce({ response: { status: 503 } })
    renderModal({ withToaster: true })
    openCopyView()

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Alfa' }))
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar a 1 turmas' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Aplicar' }))

    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(/Ocorreu um erro inesperado/),
    ).toBeInTheDocument()
  })
})
