import { render, screen, fireEvent } from '@testing-library/react'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import RoomForm from '../components/Forms/RoomForm'

const { useRoomTypesMock } = vi.hoisted(() => ({ useRoomTypesMock: vi.fn() }))

vi.mock('../features/catalog/data', () => ({ useRoomTypes: useRoomTypesMock }))

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
    useRoomTypesMock.mockReturnValue({ data: roomTypes, isLoading: false, isError: false, refetch: vi.fn() })
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

    fireEvent.click(screen.getByText('Criar Sala'))

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

  it('mostra "Atualizar Sala" em modo edicao', () => {
    const editData = { name: 'Sala X', room_type: roomTypes[0], capacity: 25 }
    render(<RoomForm {...defaultProps} initialData={editData} />)

    expect(screen.getByText('Atualizar Sala')).toBeInTheDocument()
  })

  it('anuncia o carregamento e impede submissao enquanto carrega os tipos', () => {
    useRoomTypesMock.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    render(<RoomForm {...defaultProps} />)

    expect(screen.getByRole('status')).toHaveTextContent(/a carregar tipos de sala/i)
    expect(screen.getByLabelText(/tipo de sala/i)).toBeDisabled()
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveAttribute('aria-describedby', 'room-types-loading')
    expect(screen.getByRole('button', { name: 'Criar Sala' })).toBeDisabled()
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
    expect(screen.getByRole('button', { name: 'Criar Sala' })).toBeDisabled()
  })
})
