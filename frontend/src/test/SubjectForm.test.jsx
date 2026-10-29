import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SubjectForm from '../components/Forms/SubjectForm'
import { EMPTY_MODULE, normalizeModule } from '../utils/subjectModules'

const { useRoomTypesMock } = vi.hoisted(() => ({ useRoomTypesMock: vi.fn() }))

vi.mock('../features/catalog/data', () => ({ useRoomTypes: useRoomTypesMock }))

const roomTypes = [
  { id: 11, name: 'Normal', is_normal: true },
  { id: 24, name: 'Oficina', is_normal: false },
]

const renderForm = (props = {}) => render(<SubjectForm initialData={null} onSubmit={vi.fn()} onCancel={vi.fn()} isLoading={false} {...props} />)

describe('SubjectForm helpers', () => {
  it('normalizes valid modules and rejects invalid ones', () => {
    expect(EMPTY_MODULE).toEqual({ name: '', code: '', hours_total: '' })
    expect(normalizeModule({ id: 7, name: ' M1 ', code: ' C1 ', hours_total: '25' })).toEqual({ id: 7, name: 'M1', code: 'C1', hours_total: 25 })
    expect(normalizeModule({ name: 'M1', hours_total: '0' })).toBeNull()
  })
})

describe('SubjectForm', () => {
  beforeEach(() => {
    useRoomTypesMock.mockReturnValue({ data: roomTypes, isLoading: false, isError: false, refetch: vi.fn() })
  })

  it('shows both sections and initializes edit data lazily', () => {
    renderForm({ initialData: { name: 'Matemática', room_type: roomTypes[1], modules: [{ id: 1, name: 'M1', code: 'P01', hours_total: 25, order: 9 }] } })
    expect(screen.getByRole('group', { name: 'Dados gerais' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Módulos' })).toBeInTheDocument()
    expect(screen.getByLabelText(/nome da disciplina/i)).toHaveValue('Matemática')
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('24')
    expect(screen.getByText('M1')).toBeInTheDocument()
    expect(screen.getByText('P01')).toBeInTheDocument()
    expect(screen.getByText('25h')).toBeInTheDocument()
  })

  it('adds, edits, removes, and orders modules only in the submit payload', () => {
    const onSubmit = vi.fn()
    renderForm({ onSubmit })
    fireEvent.change(screen.getByLabelText(/nome da disciplina/i), { target: { value: ' Programação ' } })
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: ' M1 ' } })
    fireEvent.change(screen.getByLabelText(/código UFCD/i), { target: { value: ' C1 ' } })
    fireEvent.change(screen.getByLabelText(/horas/i), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    fireEvent.click(screen.getByRole('button', { name: /editar M1/i }))
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: ' Módulo 1 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    fireEvent.click(screen.getByRole('button', { name: /criar disciplina/i }))
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Programação',
      room_type_id: 11,
      modules: [{ name: 'Módulo 1', code: 'C1', hours_total: 25, order: 0 }],
    })
    fireEvent.click(screen.getByRole('button', { name: /remover módulo 1/i }))
    expect(screen.queryByText('Módulo 1')).not.toBeInTheDocument()
  })

  it('validates modules and supports cancel/loading', () => {
    const onCancel = vi.fn()
    renderForm({ onCancel, isLoading: true })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/número de horas válido/i)
    expect(screen.getByRole('button', { name: /a guardar/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /^cancelar$/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('associates the module error with the module group', () => {
    renderForm()
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))

    const moduleName = screen.getByLabelText(/nome do módulo/i)
    expect(screen.getByRole('alert')).toHaveTextContent(/número de horas válido/i)
    expect(moduleName).toHaveAttribute('aria-invalid', 'true')
    expect(moduleName).toHaveClass('is-invalid')
    expect(moduleName).toHaveFocus()
  })

  it('associates the subject name error through the real submission', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.click(screen.getByRole('button', { name: /criar disciplina/i }))

    const nameInput = screen.getByLabelText(/nome da disciplina/i)
    expect(screen.getByRole('alert')).toHaveTextContent(/nome da disciplina é obrigatório/i)
    expect(nameInput).toHaveAttribute('aria-invalid', 'true')
    expect(nameInput).toHaveClass('is-invalid')
    expect(nameInput).toHaveFocus()

    await user.type(nameInput, 'Programação')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(nameInput).not.toHaveClass('is-invalid')
  })

  it('keeps the curriculum inspectable without exposing edit controls in read-only mode', () => {
    renderForm({
      readOnly: true,
      initialData: {
        name: 'Programação',
        room_type: roomTypes[1],
        modules: [{ id: 1, name: 'Fundamentos de programação', code: 'UFCD-PROG-1', hours_total: 2 }],
      },
    })

    expect(screen.getByLabelText(/nome da disciplina/i)).toBeDisabled()
    expect(screen.getByText('Fundamentos de programação')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /criar disciplina/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar alterações' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fechar', exact: true })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /editar fundamentos/i })).not.toBeInTheDocument()
  })

  it('mantém botões de editar e remover lado a lado mesmo com nome de módulo muito longo', () => {
    const { container } = renderForm({
      initialData: {
        name: 'Programação',
        modules: [{ id: 1, name: 'dwadadawdawdawdawdaw', code: '12314', hours_total: 20 }],
      },
    })

    const actionsContainer = container.querySelector('.module-item-card .text-nowrap')
    expect(actionsContainer).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /editar dwadadawdawdawdawdaw/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remover dwadadawdawdawdawdaw/i })).toBeInTheDocument()
  })

  it('uses the school types and sends the selected type id', () => {
    const onSubmit = vi.fn()
    renderForm({ onSubmit })

    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('11')
    expect(screen.getByRole('option', { name: 'Oficina' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/tipo de sala/i), { target: { value: '24' } })
    fireEvent.change(screen.getByLabelText(/nome da disciplina/i), { target: { value: 'Cerâmica' } })
    fireEvent.click(screen.getByRole('button', { name: /criar disciplina/i }))

    expect(onSubmit).toHaveBeenCalledWith({ name: 'Cerâmica', room_type_id: 24, modules: [] })
  })

  it('anuncia o carregamento e impede submissao enquanto carrega os tipos', () => {
    useRoomTypesMock.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    renderForm()

    expect(screen.getByRole('status')).toHaveTextContent(/a carregar tipos de sala/i)
    expect(screen.getByLabelText(/tipo de sala/i)).toBeDisabled()
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-describedby', 'room-types-loading')
    expect(screen.getByRole('button', { name: /criar disciplina/i })).toBeDisabled()
  })

  it('anuncia o erro e permite voltar a carregar os tipos', () => {
    const refetch = vi.fn()
    useRoomTypesMock.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch })
    renderForm()

    expect(screen.getByRole('alert')).toHaveTextContent(/não foi possível carregar os tipos de sala/i)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-describedby', 'room-types-error')
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))
    expect(refetch).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: /criar disciplina/i })).toBeDisabled()
  })
})
