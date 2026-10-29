import { render, screen, fireEvent } from '@testing-library/react'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import RoomForm from '../components/Forms/RoomForm'

const { useRoomTypesMock, createType } = vi.hoisted(() => ({ useRoomTypesMock: vi.fn(), createType: vi.fn() }))

vi.mock('../features/catalog/data', () => ({
  useRoomTypes: useRoomTypesMock,
  useCreateRoomType: () => ({ mutateAsync: createType, isPending: false }),
  useUpdateRoomType: () => ({ isPending: false }),
  useDeleteRoomType: () => ({ isPending: false }),
}))

const roomTypes = [
  { id: 11, name: 'Normal', is_normal: true },
  { id: 24, name: 'Oficina', is_normal: false },
]

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('RoomForm', () => {
  beforeEach(() => {
    createType.mockReset().mockResolvedValue({ id: 37, name: 'Artes' })
    useRoomTypesMock.mockReturnValue({ data: roomTypes, isLoading: false, isError: false, refetch: vi.fn() })
  })

  it('creates and selects a type inside the room form without submitting the room', async () => {
    const onSubmit = vi.fn()
    render(<RoomForm {...defaultProps} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText(/nome da sala/i), { target: { value: 'Sala Artes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar tipo de sala' }))
    fireEvent.change(screen.getByLabelText('Nome do novo tipo'), { target: { value: 'Artes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar tipo de sala' }))
    expect(await screen.findByRole('option', { name: 'Artes' })).toBeInTheDocument()
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('37')
    expect(createType).toHaveBeenCalledWith({ name: 'Artes' })
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByLabelText(/nome da sala/i)).toHaveValue('Sala Artes')
  })

  it('keeps a refused type name and the room draft for correction', async () => {
    createType.mockRejectedValue({ response: { status: 409, data: { detail: { code: 'room_type_name_taken' } } } })
    const onSubmit = vi.fn()
    render(<RoomForm {...defaultProps} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText(/nome da sala/i), { target: { value: 'Sala Artes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar tipo de sala' }))
    fireEvent.change(screen.getByLabelText('Nome do novo tipo'), { target: { value: 'Artes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar tipo de sala' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe um tipo de sala com este nome.')
    expect(screen.getByLabelText('Nome do novo tipo')).toHaveValue('Artes')
    expect(screen.getByLabelText(/nome da sala/i)).toHaveValue('Sala Artes')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits the visible Normal type if the selected type was removed', () => {
    const onSubmit = vi.fn()
    const view = render(<RoomForm {...defaultProps} initialData={{ name: 'Sala X', room_type: roomTypes[1], capacity: 25 }} onSubmit={onSubmit} />)
    useRoomTypesMock.mockReturnValue({ data: [roomTypes[0]], isLoading: false, isError: false, refetch: vi.fn() })
    view.rerender(<RoomForm {...defaultProps} initialData={{ name: 'Sala X', room_type: roomTypes[1], capacity: 25 }} onSubmit={onSubmit} />)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('11')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar alterações' }))
    expect(onSubmit).toHaveBeenCalledWith({ name: 'Sala X', room_type_id: 11, capacity: 25 })
  })

  it('renderiza campos principais com valores iniciais validos', () => {
    render(<RoomForm {...defaultProps} />)

    expect(screen.getByLabelText(/nome da sala/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/lota/i)).toHaveValue(30)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('11')
    expect(screen.getByRole('option', { name: 'Oficina' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Laboratório' })).not.toBeInTheDocument()
  })

  it('envia o id do tipo da escola e lotacao numerica', () => {
    const onSubmit = vi.fn()
    render(<RoomForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByLabelText(/nome da sala/i), {
      target: { value: 'Lab 3' },
    })
    fireEvent.change(screen.getByLabelText(/lota/i), {
      target: { value: '24' },
    })
    fireEvent.change(screen.getByLabelText(/tipo de sala/i), {
      target: { value: '24' },
    })

    fireEvent.click(screen.getByText('Criar sala'))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Lab 3',
      capacity: 24,
      room_type_id: 24,
    })
  })

  it('popula dados na edicao', () => {
    const editData = { name: 'Sala 200', room_type: roomTypes[1], capacity: 30 }
    render(<RoomForm {...defaultProps} initialData={editData} />)

    expect(screen.getByLabelText(/nome da sala/i)).toHaveValue('Sala 200')
    expect(screen.getByLabelText(/lota/i)).toHaveValue(30)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('24')
  })

  it('botao Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<RoomForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra "Guardar alterações" em modo edicao', () => {
    const editData = { name: 'Sala X', room_type: roomTypes[0], capacity: 25 }
    render(<RoomForm {...defaultProps} initialData={editData} />)

    expect(screen.getByText('Guardar alterações')).toBeInTheDocument()
  })

  it('anuncia o carregamento e impede submissao enquanto carrega os tipos', () => {
    useRoomTypesMock.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    render(<RoomForm {...defaultProps} />)

    expect(screen.getByRole('status')).toHaveTextContent(/a carregar tipos de sala/i)
    expect(screen.getByLabelText(/tipo de sala/i)).toBeDisabled()
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-describedby', 'room-types-loading')
    expect(screen.getByRole('button', { name: 'Criar sala' })).toBeDisabled()
  })

  it('anuncia o erro e permite voltar a carregar os tipos', () => {
    const refetch = vi.fn()
    useRoomTypesMock.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch })
    render(<RoomForm {...defaultProps} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/não foi possível carregar os tipos de sala/i)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-describedby', 'room-types-error')
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))
    expect(refetch).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Criar sala' })).toBeDisabled()
  })
})
