// Ficheiro: frontend/src/test/ClassInCourseForm.test.jsx
/**
 * TESTES — ClassInCourseForm
 * ==========================
 * Formulário de criação de turma dentro do wizard de curso.
 * Verifica campos de grau, ano de início/fim e submissão contextual a um curso.
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ClassInCourseForm from '../components/Forms/ClassInCourseForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
  courseId: 1,
  gradeLevel: 10,
}

describe('ClassInCourseForm', () => {
  it('renderiza campos de nome, tamanho e ano', () => {
    render(<ClassInCourseForm {...defaultProps} />)
    expect(screen.getByText('Nome da Turma')).toBeInTheDocument()
    expect(screen.getByText('Nº Alunos')).toBeInTheDocument()
    expect(screen.getByText('Ano (10-12)')).toBeInTheDocument()
  })

  it('chama onSubmit com payload normalizado e numerico', () => {
    const onSubmit = vi.fn()
    render(<ClassInCourseForm {...defaultProps} onSubmit={onSubmit} />)

    const nameInput = screen.getByRole('textbox')
    fireEvent.change(nameInput, {
      target: { value: ' Turma CIF A ' },
    })
    fireEvent.change(screen.getByLabelText(/n.*alunos/i), { target: { value: '28' } })
    fireEvent.change(screen.getByLabelText(/ano/i), { target: { value: '11' } })
    fireEvent.change(screen.getByLabelText(/in/i), { target: { value: '2026' } })
    fireEvent.change(screen.getByLabelText(/fim/i), { target: { value: '2029' } })

    fireEvent.click(screen.getByRole('button', { name: /criar turma/i }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Turma CIF A',
      size: 28,
      grade_level: 11,
      start_year: 2026,
      end_year: 2029,
    })
  })

  it('bloqueia submissao com ano de fim anterior ou igual ao inicio', () => {
    const onSubmit = vi.fn()
    render(<ClassInCourseForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Turma CIF B' } })
    fireEvent.change(screen.getByLabelText(/in/i), { target: { value: '2027' } })
    fireEvent.change(screen.getByLabelText(/fim/i), { target: { value: '2027' } })

    fireEvent.click(screen.getByRole('button', { name: /criar turma/i }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/ano de fim/i)).toBeInTheDocument()
  })

  it('popula campos na edição', () => {
    const editData = {
      name: 'Turma Edit CIF',
      size: 20,
      start_year: 2026,
      end_year: 2029,
    }
    render(<ClassInCourseForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('Turma Edit CIF')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<ClassInCourseForm {...defaultProps} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
