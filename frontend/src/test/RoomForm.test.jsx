// Ficheiro: frontend/src/test/RoomForm.test.jsx
/**
 * TESTES — RoomForm
 * =================
 * Formulário simples (sem wizard).
 * Verifica campos, submit e edição.
 */

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
  it('renderiza campo de nome e dropdown de tipo', () => {
    render(<RoomForm {...defaultProps} />)
    expect(screen.getByPlaceholderText(/C4, Lab Química/i)).toBeInTheDocument()
    // CFormSelect renderiza como <select>
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(1)
  })

  it('chama onSubmit ao submeter com dados', () => {
    const onSubmit = vi.fn()
    render(<RoomForm {...defaultProps} onSubmit={onSubmit} />)
    
    fireEvent.change(screen.getByPlaceholderText(/C4, Lab Química/i), {
      target: { value: 'Lab 3' },
    })
    // Submit via button
    fireEvent.click(screen.getByText('Criar Sala'))
    expect(onSubmit).toHaveBeenCalled()
  })

  it('popula dados na edição', () => {
    const editData = { name: 'Sala 200', type: 'lab', capacity: 30 }
    render(<RoomForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('Sala 200')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<RoomForm {...defaultProps} onCancel={onCancel} />)
    
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra "Atualizar Sala" em modo edição', () => {
    const editData = { name: 'Sala X', type: 'normal', capacity: 25 }
    render(<RoomForm {...defaultProps} initialData={editData} />)
    expect(screen.getByText('Atualizar Sala')).toBeInTheDocument()
  })
})
