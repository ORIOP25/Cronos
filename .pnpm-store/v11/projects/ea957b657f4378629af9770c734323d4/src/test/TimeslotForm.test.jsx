import { screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import TimeslotForm from '../components/Forms/TimeslotForm'
import { renderWithProviders } from './testUtils'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('TimeslotForm', () => {
  it('renderiza campos com valores iniciais validos', () => {
    renderWithProviders(<TimeslotForm {...defaultProps} />)

    expect(screen.getByLabelText(/dia da semana/i)).toHaveValue('0')
    expect(screen.getByLabelText(/hora in/i)).toHaveValue('08:00')
    expect(screen.getByLabelText(/hora fim/i)).toHaveValue('08:45')
    expect(screen.getByText('Cancelar')).toBeInTheDocument()
  })

  it('chama onSubmit com dia numerico e horas normalizadas', () => {
    const onSubmit = vi.fn()
    renderWithProviders(<TimeslotForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByLabelText(/dia da semana/i), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText(/hora in/i), {
      target: { value: '09:00' },
    })
    fireEvent.change(screen.getByLabelText(/hora fim/i), {
      target: { value: '10:15' },
    })

    fireEvent.click(screen.getByRole('button', { name: /criar bloco/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      day_of_week: 2,
      start_time: '09:00:00',
      end_time: '10:15:00',
    })
  })

  it('preserva horas que ja incluem segundos ao editar', () => {
    const onSubmit = vi.fn()
    const editData = {
      day_of_week: 1,
      start_time: '09:00:00',
      end_time: '10:00:00',
    }
    renderWithProviders(
      <TimeslotForm {...defaultProps} initialData={editData} onSubmit={onSubmit} />
    )

    expect(screen.getByLabelText(/dia da semana/i)).toHaveValue('1')
    expect(screen.getByLabelText(/hora in/i)).toHaveValue('09:00')
    expect(screen.getByLabelText(/hora fim/i)).toHaveValue('10:00')

    fireEvent.click(screen.getByRole('button', { name: /atualizar bloco/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      day_of_week: 1,
      start_time: '09:00:00',
      end_time: '10:00:00',
    })
  })

  it('botao Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    renderWithProviders(<TimeslotForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra estado de loading', () => {
    renderWithProviders(<TimeslotForm {...defaultProps} isLoading />)

    expect(screen.getByRole('button', { name: /a gravar/i })).toBeDisabled()
  })
})
