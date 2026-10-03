import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CourseForm from '../components/Forms/CourseForm'

const renderForm = (props = {}) => render(<CourseForm onSubmit={vi.fn()} onCancel={vi.fn()} isLoading={false} {...props} />)

describe('CourseForm', () => {
  it('shows general data and initial classes together', () => {
    renderForm()
    expect(screen.getByRole('group', { name: 'Dados gerais' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Turmas iniciais' })).toBeInTheDocument()
    expect(screen.queryByText(/passo|anterior|próximo/i)).not.toBeInTheDocument()
  })

  it('validates class drafts and can add and remove a class', () => {
    renderForm()
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/nome da turma/i)

    fireEvent.change(screen.getByLabelText(/nome turma/i), { target: { value: '10 TI' } })
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))
    expect(screen.getByText(/10 TI.*10.*25 alunos/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /remover 10 TI/i }))
    expect(screen.queryByText(/10 TI.*25 alunos/i)).not.toBeInTheDocument()
  })

  it('submits a trimmed backend-shaped payload without subject_ids', () => {
    const onSubmit = vi.fn()
    renderForm({ onSubmit })
    fireEvent.change(screen.getByLabelText(/nome do curso/i), { target: { value: '  Técnico de Informática  ' } })
    fireEvent.change(screen.getByLabelText(/sigla/i), { target: { value: ' TI ' } })
    fireEvent.change(screen.getByLabelText(/nome turma/i), { target: { value: '10 TI' } })
    fireEvent.change(screen.getByLabelText(/ano de início/i), { target: { value: '2026' } })
    fireEvent.change(screen.getByLabelText(/ano de fim/i), { target: { value: '2029' } })
    fireEvent.change(screen.getByLabelText(/alunos/i), { target: { value: '24' } })
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))
    fireEvent.click(screen.getByRole('button', { name: /criar curso/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Técnico de Informática',
      abbreviation: 'TI',
      classes_config: [{ name: '10 TI', grade_level: 10, start_year: 2026, end_year: 2029, size: 24 }],
    })
  })

  it('associates the course error with its field and focuses it', () => {
    renderForm()
    const nameInput = screen.getByLabelText(/nome do curso/i)
    fireEvent.submit(nameInput.closest('form'))

    expect(screen.getByRole('alert')).toHaveTextContent(/nome do curso é obrigatório/i)
    expect(nameInput).toHaveAttribute('aria-invalid', 'true')
    expect(nameInput).toHaveFocus()

    fireEvent.change(nameInput, { target: { value: 'Técnico' } })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('associates the class error with the class name field', () => {
    renderForm()
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))

    const classNameInput = screen.getByLabelText(/nome turma/i)
    expect(screen.getByRole('alert')).toHaveTextContent(/nome da turma/i)
    expect(classNameInput).toHaveAttribute('aria-invalid', 'true')
    expect(classNameInput).toHaveFocus()
  })

  it('supports cancel and loading state', () => {
    const onCancel = vi.fn()
    renderForm({ onCancel, isLoading: true })
    expect(screen.getByRole('button', { name: /a gravar/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
