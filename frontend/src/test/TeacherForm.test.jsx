// Ficheiro: frontend/src/test/TeacherForm.test.jsx
/**
 * TESTES — TeacherForm
 * =====================
 * Formulário de professor com campos de nome, email, competências, conta de acesso.
 * Requer QueryClientProvider (usa useSubjects internamente).
 */

import { screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import TeacherForm from '../components/Forms/TeacherForm'
import { renderWithProviders } from './testUtils'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('TeacherForm', () => {
  it('renderiza sem crash (com QueryClientProvider)', () => {
    renderWithProviders(<TeacherForm {...defaultProps} />)
    expect(screen.getByText('Cancelar')).toBeInTheDocument()
  })

  it('tem campos de nome e email', () => {
    renderWithProviders(<TeacherForm {...defaultProps} />)
    expect(screen.getByPlaceholderText(/João Silva/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/joao@escola.pt/i)).toBeInTheDocument()
  })

  it('popula dados na edição', () => {
    const editData = { name: 'Prof. Silva', email: 'silva@escola.pt', subject_ids: [] }
    renderWithProviders(<TeacherForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('Prof. Silva')).toBeInTheDocument()
    expect(screen.getByDisplayValue('silva@escola.pt')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    renderWithProviders(<TeacherForm {...defaultProps} onCancel={onCancel} />)
    
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra botões quando não está a carregar', () => {
    renderWithProviders(<TeacherForm {...defaultProps} isLoading={false} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
  })

  it('tem switch de conta de acesso', () => {
    renderWithProviders(<TeacherForm {...defaultProps} />)
    const switches = screen.getAllByRole('checkbox')
    expect(switches.length).toBeGreaterThanOrEqual(1)
  })
})
