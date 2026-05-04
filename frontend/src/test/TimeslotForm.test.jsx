// Ficheiro: frontend/src/test/TimeslotForm.test.jsx
/**
 * TESTES — TimeslotForm
 * =====================
 * Formulário de criação e edição de timeslots (horários de aula).
 * Verifica campos, validação e submissão via API.
 */

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
  it('renderiza campos de hora inicio e fim', () => {
    renderWithProviders(<TimeslotForm {...defaultProps} />)
    expect(screen.getByText('Hora Início')).toBeInTheDocument()
    expect(screen.getByText('Hora Fim')).toBeInTheDocument()
    expect(screen.getByText('Cancelar')).toBeInTheDocument()
  })

  it('tem dropdown de dia da semana', () => {
    renderWithProviders(<TimeslotForm {...defaultProps} />)
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(1)
  })

  it('chama onSubmit com dados válidos', () => {
    const onSubmit = vi.fn()
    renderWithProviders(<TimeslotForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByRole('button', { name: /criar bloco/i }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('popula dados na edição', () => {
    const editData = {
      day_of_week: 1,
      start_time: '09:00',
      end_time: '10:00',
    }
    renderWithProviders(<TimeslotForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('09:00')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    renderWithProviders(<TimeslotForm {...defaultProps} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
