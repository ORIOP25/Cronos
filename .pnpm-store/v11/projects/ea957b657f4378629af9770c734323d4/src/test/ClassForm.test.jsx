import { screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ClassForm from '../components/Forms/ClassForm'
import { renderWithProviders } from './testUtils'

vi.mock('../hooks/useSchoolData', () => ({
  useCourses: () => ({
    data: [
      { id: 1, name: 'Tecnico Informatica' },
      { id: 2, name: 'Artes Visuais' },
    ],
  }),
}))

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('ClassForm', () => {
  it('renderiza todos os campos exigidos pelo backend', () => {
    renderWithProviders(<ClassForm {...defaultProps} />)

    expect(screen.getByLabelText(/nome da turma/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/alunos/i)).toHaveValue(25)
    expect(screen.getByLabelText(/curso associado/i)).toHaveValue('')
    expect(screen.getByLabelText(/ano \(10-12\)/i)).toHaveValue(10)
    expect(screen.getByLabelText(/inicio/i)).toHaveValue(new Date().getFullYear())
    expect(screen.getByLabelText(/fim/i)).toHaveValue(new Date().getFullYear() + 3)
  })

  it('chama onSubmit com payload completo e tipos corretos', () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ClassForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByLabelText(/nome da turma/i), {
      target: { value: 'Turma TI A' },
    })
    fireEvent.change(screen.getByLabelText(/alunos/i), {
      target: { value: '28' },
    })
    fireEvent.change(screen.getByLabelText(/curso associado/i), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText(/ano \(10-12\)/i), {
      target: { value: '11' },
    })
    fireEvent.change(screen.getByLabelText(/inicio/i), {
      target: { value: '2026' },
    })
    fireEvent.change(screen.getByLabelText(/fim/i), {
      target: { value: '2029' },
    })

    fireEvent.click(screen.getByRole('button', { name: /criar turma/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Turma TI A',
      size: 28,
      course_id: 1,
      grade_level: 11,
      start_year: 2026,
      end_year: 2029,
    })
  })

  it('popula campos na edicao', () => {
    const editData = {
      name: 'Turma Existente',
      size: 25,
      course_id: 2,
      grade_level: 10,
      start_year: 2025,
      end_year: 2028,
    }
    renderWithProviders(<ClassForm {...defaultProps} initialData={editData} />)

    expect(screen.getByLabelText(/nome da turma/i)).toHaveValue('Turma Existente')
    expect(screen.getByLabelText(/alunos/i)).toHaveValue(25)
    expect(screen.getByLabelText(/curso associado/i)).toHaveValue('2')
    expect(screen.getByLabelText(/ano \(10-12\)/i)).toHaveValue(10)
    expect(screen.getByLabelText(/inicio/i)).toHaveValue(2025)
    expect(screen.getByLabelText(/fim/i)).toHaveValue(2028)
  })

  it('botao Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    renderWithProviders(<ClassForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('mostra "Atualizar Turma" em modo edicao', () => {
    const editData = {
      name: 'T. Edit',
      size: 20,
      course_id: 1,
      grade_level: 10,
      start_year: 2025,
      end_year: 2028,
    }
    renderWithProviders(<ClassForm {...defaultProps} initialData={editData} />)

    expect(screen.getByText('Atualizar Turma')).toBeInTheDocument()
  })
})
