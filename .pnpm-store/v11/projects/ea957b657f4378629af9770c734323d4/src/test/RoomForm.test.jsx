import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import RoomForm from '../components/Forms/RoomForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('RoomForm', () => {
  it('renderiza campos principais com valores iniciais validos', () => {
    render(<RoomForm {...defaultProps} />)

    expect(screen.getByLabelText(/nome da sala/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/lota/i)).toHaveValue(30)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('normal')
  })

  it('chama onSubmit com payload completo e lotacao numerica', () => {
    const onSubmit = vi.fn()
    render(<RoomForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByLabelText(/nome da sala/i), {
      target: { value: 'Lab 3' },
    })
    fireEvent.change(screen.getByLabelText(/lota/i), {
      target: { value: '24' },
    })
    fireEvent.change(screen.getByLabelText(/tipo de sala/i), {
      target: { value: 'lab' },
    })

    fireEvent.click(screen.getByText('Criar Sala'))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Lab 3',
      capacity: 24,
      type: 'lab',
    })
  })

  it('popula dados na edicao', () => {
    const editData = { name: 'Sala 200', type: 'lab', capacity: 30 }
    render(<RoomForm {...defaultProps} initialData={editData} />)

    expect(screen.getByLabelText(/nome da sala/i)).toHaveValue('Sala 200')
    expect(screen.getByLabelText(/lota/i)).toHaveValue(30)
    expect(screen.getByLabelText(/tipo de sala/i)).toHaveValue('lab')
  })

  it('botao Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<RoomForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra "Atualizar Sala" em modo edicao', () => {
    const editData = { name: 'Sala X', type: 'normal', capacity: 25 }
    render(<RoomForm {...defaultProps} initialData={editData} />)

    expect(screen.getByText('Atualizar Sala')).toBeInTheDocument()
  })
})
