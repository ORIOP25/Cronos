// Ficheiro: frontend/src/test/ClassForm.test.jsx
/**
 * TESTES — ClassForm
 * ==================
 * Formulário de criação e edição de turmas.
 * Verifica campos obrigatórios, validação e submissão.
 */

import { screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ClassForm from '../components/Forms/ClassForm'
import { renderWithProviders } from './testUtils'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
  courseId: 1,
}

describe('ClassForm', () => {
  it('renderiza campos obrigatórios', () => {
    renderWithProviders(<ClassForm {...defaultProps} />)
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Cancelar')).toBeInTheDocument()
  })

  it('chama onSubmit com dados válidos', () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ClassForm {...defaultProps} onSubmit={onSubmit} />)

    const nameInput = screen.getByRole('textbox')
    fireEvent.change(nameInput, {
      target: { value: 'Turma TI A' },
    })

    fireEvent.click(screen.getByRole('button', { name: /criar turma/i }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('popula campos na edição', () => {
    const editData = {
      name: 'Turma Existente',
      size: 25,
      grade_level: 10,
      start_year: 2025,
      end_year: 2028,
    }
    renderWithProviders(<ClassForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('Turma Existente')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    renderWithProviders(<ClassForm {...defaultProps} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra "Atualizar Turma" em modo edição', () => {
    const editData = { name: 'T. Edit', size: 20, grade_level: 10 }
    renderWithProviders(<ClassForm {...defaultProps} initialData={editData} />)
    expect(screen.getByText('Atualizar Turma')).toBeInTheDocument()
  })
})
