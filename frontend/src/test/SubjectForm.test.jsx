import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SubjectForm from '../components/Forms/SubjectForm'
import { EMPTY_MODULE, normalizeModule } from '../utils/subjectModules'

const renderForm = (props = {}) => render(<SubjectForm initialData={null} onSubmit={vi.fn()} onCancel={vi.fn()} isLoading={false} {...props} />)

describe('SubjectForm helpers', () => {
  it('normalizes valid modules and rejects invalid ones', () => {
    expect(EMPTY_MODULE).toEqual({ name: '', code: '', hours_total: '' })
    expect(normalizeModule({ id: 7, name: ' M1 ', code: ' C1 ', hours_total: '25' })).toEqual({ id: 7, name: 'M1', code: 'C1', hours_total: 25 })
    expect(normalizeModule({ name: 'M1', hours_total: '0' })).toBeNull()
  })
})

describe('SubjectForm', () => {
  it('shows both sections and initializes edit data lazily', () => {
    renderForm({ initialData: { name: 'Matemática', required_room_type: 'lab', modules: [{ id: 1, name: 'M1', code: 'P01', hours_total: 25, order: 9 }] } })
    expect(screen.getByRole('group', { name: 'Dados gerais' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Módulos' })).toBeInTheDocument()
    expect(screen.getByLabelText(/nome da disciplina/i)).toHaveValue('Matemática')
    expect(screen.getByLabelText(/sala preferencial/i)).toHaveValue('lab')
    expect(screen.getByText(/M1.*P01.*25h/i)).toBeInTheDocument()
  })

  it('adds, edits, removes, and orders modules only in the submit payload', () => {
    const onSubmit = vi.fn()
    renderForm({ onSubmit })
    fireEvent.change(screen.getByLabelText(/nome da disciplina/i), { target: { value: ' Programação ' } })
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: ' M1 ' } })
    fireEvent.change(screen.getByLabelText(/código UFCD/i), { target: { value: ' C1 ' } })
    fireEvent.change(screen.getByLabelText(/horas/i), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    fireEvent.click(screen.getByRole('button', { name: /editar M1/i }))
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: ' Módulo 1 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    fireEvent.click(screen.getByRole('button', { name: /guardar disciplina/i }))
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Programação',
      required_room_type: 'normal',
      modules: [{ name: 'Módulo 1', code: 'C1', hours_total: 25, order: 0 }],
    })
    fireEvent.click(screen.getByRole('button', { name: /remover módulo 1/i }))
    expect(screen.queryByText(/Módulo 1.*25h/i)).not.toBeInTheDocument()
  })

  it('validates modules and supports cancel/loading', () => {
    const onCancel = vi.fn()
    renderForm({ onCancel, isLoading: true })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/número de horas válido/i)
    expect(screen.getByRole('button', { name: /a guardar/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /^cancelar$/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
