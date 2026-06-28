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

vi.mock('../hooks/useSchoolData', () => ({
  useSubjects: () => ({
    data: [
      { id: 1, name: 'Matemática' },
      { id: 2, name: 'Português' },
    ],
    isLoading: false,
  }),
}))

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('TeacherForm', () => {
  it('renderiza o formulário com ações principais', () => {
    renderWithProviders(<TeacherForm {...defaultProps} />)
    expect(screen.getByLabelText(/nome completo/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/email de login/i)).toBeInTheDocument()
    expect(screen.getByText('Cancelar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar professor/i })).toBeInTheDocument()
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
    expect(screen.getByRole('checkbox', { name: /criar conta de acesso/i })).toBeInTheDocument()
  })

  it('mostra password obrigatória quando a conta de acesso é ativada', () => {
    renderWithProviders(<TeacherForm {...defaultProps} />)

    fireEvent.click(screen.getByRole('checkbox', { name: /criar conta de acesso/i }))

    expect(screen.getByLabelText(/password de acesso/i)).toBeRequired()
  })

  it('chama onSubmit com dados e competências selecionadas', () => {
    const onSubmit = vi.fn()
    renderWithProviders(<TeacherForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByLabelText(/nome completo/i), { target: { value: 'Prof. Matos' } })
    fireEvent.change(screen.getByLabelText(/email de login/i), { target: { value: 'matos@escola.pt' } })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Matemática' }))
    fireEvent.click(screen.getByRole('button', { name: /guardar professor/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Prof. Matos',
      email: 'matos@escola.pt',
      password: '',
      create_user_account: false,
      subject_ids: [1],
    })
  })
})
