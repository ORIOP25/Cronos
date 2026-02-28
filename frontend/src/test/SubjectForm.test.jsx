// Ficheiro: frontend/src/test/SubjectForm.test.jsx
/**
 * TESTES — SubjectForm (Wizard 2 Passos)
 * =======================================
 * 1. Renderiza passo 1 (Dados Gerais) por defeito
 * 2. Navega para passo 2 (Módulos)
 * 3. Não avança sem nome da disciplina
 * 4. Dropdown de tipo de sala funciona
 * 5. Passo 2 tem formulário de adicionar módulos
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import SubjectForm from '../components/Forms/SubjectForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('SubjectForm — Wizard', () => {
  it('renderiza passo 1 (Dados Gerais) por defeito', () => {
    render(<SubjectForm {...defaultProps} />)
    expect(screen.getByText('1. Dados Gerais')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Matemática A/i)).toBeInTheDocument()
  })

  it('badge de passos visível', () => {
    render(<SubjectForm {...defaultProps} />)
    expect(screen.getByText('1. Dados Gerais')).toBeInTheDocument()
    expect(screen.getByText('2. Módulos')).toBeInTheDocument()
  })

  it('avança para passo 2 (Módulos) quando nome preenchido', () => {
    render(<SubjectForm {...defaultProps} />)
    
    fireEvent.change(screen.getByPlaceholderText(/Matemática A/i), {
      target: { value: 'Programação' },
    })
    fireEvent.click(screen.getByText(/Próximo: Módulos/i))
    
    expect(screen.getByText(/Adicionar Módulos/i)).toBeInTheDocument()
  })

  it('botão "Próximo" desativado sem nome', () => {
    render(<SubjectForm {...defaultProps} />)
    const nextBtn = screen.getByText(/Próximo: Módulos/i)
    expect(nextBtn).toBeDisabled()
  })

  it('passo 2 tem campos para nome, código e horas do módulo', () => {
    render(<SubjectForm {...defaultProps} />)
    
    fireEvent.change(screen.getByPlaceholderText(/Matemática A/i), {
      target: { value: 'Física' },
    })
    fireEvent.click(screen.getByText(/Próximo: Módulos/i))
    
    expect(screen.getByPlaceholderText(/Geometria/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('001')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('H')).toBeInTheDocument()
  })

  it('dropdown de tipo de sala contém opções corretas', () => {
    render(<SubjectForm {...defaultProps} />)
    const select = screen.getByRole('combobox')
    expect(select).toBeInTheDocument()
    // CoreUI renderiza options dentro do select
    expect(select.options.length).toBeGreaterThanOrEqual(4)
  })

  it('popula campos na edição (initialData)', () => {
    const editData = {
      name: 'Matemática',
      required_room_type: 'normal',
      modules: [
        { id: 1, name: 'M1', code: 'P01', hours_total: 25, order: 0 },
      ],
    }
    render(<SubjectForm {...defaultProps} initialData={editData} />)
    expect(screen.getByDisplayValue('Matemática')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<SubjectForm {...defaultProps} onCancel={onCancel} />)
    
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
