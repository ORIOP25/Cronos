import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CourseForm from '../components/Forms/CourseForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

function fillCourseBasics(name = 'Tecnico Informatica', abbreviation = 'TI') {
  fireEvent.change(screen.getByLabelText(/nome do curso/i), {
    target: { value: name },
  })
  fireEvent.change(screen.getByLabelText(/sigla/i), {
    target: { value: abbreviation },
  })
}

function goToClassesStep() {
  fireEvent.click(screen.getByRole('button', { name: /turmas/i }))
}

describe('CourseForm - Wizard', () => {
  it('renderiza passo 1 por defeito', () => {
    render(<CourseForm {...defaultProps} />)

    expect(screen.getByText(/1\. informa/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/nome do curso/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/sigla/i)).toHaveAttribute('maxLength', '10')
    expect(screen.getByText('2. Turmas')).toBeInTheDocument()
  })

  it('nao avanca sem nome ou sigla validos', () => {
    render(<CourseForm {...defaultProps} />)

    fireEvent.click(screen.getByRole('button', { name: /turmas/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/nome do curso/i)

    fireEvent.change(screen.getByLabelText(/nome do curso/i), {
      target: { value: 'Curso X' },
    })
    fireEvent.click(screen.getByRole('button', { name: /turmas/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/sigla do curso/i)

    fireEvent.change(screen.getByLabelText(/sigla/i), {
      target: { value: 'A' },
    })
    fireEvent.click(screen.getByRole('button', { name: /turmas/i }))
    expect(screen.getByText(/pelo menos 2 caracteres/i)).toBeInTheDocument()
  })

  it('adiciona turma e submete payload completo', () => {
    const onSubmit = vi.fn()
    render(<CourseForm {...defaultProps} onSubmit={onSubmit} />)

    fillCourseBasics('  Tecnico Informatica  ', ' TI ')
    goToClassesStep()

    fireEvent.change(screen.getByLabelText(/nome turma/i), {
      target: { value: '10 TI' },
    })
    fireEvent.change(screen.getByLabelText(/ano \(10-12\)/i), {
      target: { value: '10' },
    })
    fireEvent.change(screen.getByLabelText(/2025/), {
      target: { value: '2026' },
    })
    fireEvent.change(screen.getByLabelText(/2028/), {
      target: { value: '2029' },
    })
    fireEvent.change(screen.getByLabelText(/alunos/i), {
      target: { value: '24' },
    })
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))

    expect(screen.getByText('10 TI')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /criar curso completo/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Tecnico Informatica',
      abbreviation: 'TI',
      subject_ids: [],
      classes_config: [
        {
          name: '10 TI',
          grade_level: 10,
          start_year: 2026,
          end_year: 2029,
          size: 24,
        },
      ],
    })
  })

  it('rejeita turma cujo ano de fim nao seja posterior ao inicio', () => {
    render(<CourseForm {...defaultProps} />)

    fillCourseBasics()
    goToClassesStep()

    fireEvent.change(screen.getByLabelText(/nome turma/i), {
      target: { value: '10 TI' },
    })
    fireEvent.change(screen.getByLabelText(/2025/), {
      target: { value: '2026' },
    })
    fireEvent.change(screen.getByLabelText(/2028/), {
      target: { value: '2026' },
    })
    fireEvent.click(screen.getByRole('button', { name: /adicionar turma/i }))

    expect(screen.getByText(/deve ser posterior/i)).toBeInTheDocument()
  })

  it('botao Anterior volta ao passo 1', () => {
    render(<CourseForm {...defaultProps} />)

    fillCourseBasics('Curso Y', 'CY')
    goToClassesStep()

    fireEvent.click(screen.getByText(/anterior/i))
    expect(screen.getByLabelText(/nome do curso/i)).toBeInTheDocument()
  })

  it('popula campos na edicao', () => {
    const editData = {
      name: 'TGPSI',
      abbreviation: 'TGPS',
      classes: [{ name: 'Turma A', grade_level: 10, start_year: 2025, end_year: 2028, size: 25 }],
    }
    render(<CourseForm {...defaultProps} initialData={editData} />)

    expect(screen.getByLabelText(/nome do curso/i)).toHaveValue('TGPSI')
    expect(screen.getByLabelText(/sigla/i)).toHaveValue('TGPS')
  })

  it('botao Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<CourseForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
