// Ficheiro: frontend/src/test/CourseForm.test.jsx
/**
 * TESTES — CourseForm (Wizard 2 Passos)
 * ======================================
 * 1. Renderiza passo 1 (Informações) por defeito
 * 2. Navega para passo 2 (Turmas) quando campos preenchidos
 * 3. Não avança sem nome/sigla
 * 4. Passo 2 renderiza interface de adicionar turmas
 * 5. Botão "Anterior" volta ao passo 1
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CourseForm from '../components/Forms/CourseForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('CourseForm — Wizard', () => {
  it('renderiza passo 1 (Informações) por defeito', () => {
    render(<CourseForm {...defaultProps} />)
    expect(screen.getByText('1. Informações')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Técnico em Informática/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/TGEI/i)).toBeInTheDocument()
  })

  it('tem badge "2. Turmas" visível mas inativo', () => {
    render(<CourseForm {...defaultProps} />)
    expect(screen.getByText('2. Turmas')).toBeInTheDocument()
  })

  it('avança para passo 2 quando nome e sigla preenchidos', () => {
    render(<CourseForm {...defaultProps} />)
    
    // Preencher campos obrigatórios
    fireEvent.change(screen.getByPlaceholderText(/Técnico em Informática/i), {
      target: { value: 'Técnico Informática' },
    })
    fireEvent.change(screen.getByPlaceholderText(/TGEI/i), {
      target: { value: 'TI' },
    })
    
    // Clicar em "Próximo: Turmas"
    fireEvent.click(screen.getByText(/Próximo: Turmas/i))
    
    // Deve mostrar interface de passo 2
    expect(screen.getByText(/Gerar Turmas Iniciais/i)).toBeInTheDocument()
  })

  it('passo 2 tem formulário para adicionar turmas', () => {
    render(<CourseForm {...defaultProps} />)
    
    fireEvent.change(screen.getByPlaceholderText(/Técnico em Informática/i), {
      target: { value: 'Curso X' },
    })
    fireEvent.change(screen.getByPlaceholderText(/TGEI/i), {
      target: { value: 'CX' },
    })
    fireEvent.click(screen.getByText(/Próximo: Turmas/i))
    
    // Verifica campos de turma
    expect(screen.getByPlaceholderText(/10º TGEI/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Adicionar Turma/i })).toBeInTheDocument()
  })

  it('botão Anterior volta ao passo 1', () => {
    render(<CourseForm {...defaultProps} />)
    
    fireEvent.change(screen.getByPlaceholderText(/Técnico em Informática/i), {
      target: { value: 'Curso Y' },
    })
    fireEvent.change(screen.getByPlaceholderText(/TGEI/i), {
      target: { value: 'CY' },
    })
    fireEvent.click(screen.getByText(/Próximo: Turmas/i))
    
    // Voltar
    fireEvent.click(screen.getByText(/Anterior/i))
    expect(screen.getByText(/Informações Básicas/i)).toBeInTheDocument()
  })

  it('popula campos na edição (initialData)', () => {
    const editData = {
      name: 'TGPSI',
      abbreviation: 'TGPS',
      classes: [{ name: 'Turma A', grade_level: 10, start_year: 2025, end_year: 2028, size: 25 }],
    }
    render(<CourseForm {...defaultProps} initialData={editData} />)
    
    expect(screen.getByDisplayValue('TGPSI')).toBeInTheDocument()
    expect(screen.getByDisplayValue('TGPS')).toBeInTheDocument()
  })

  it('botão Cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<CourseForm {...defaultProps} onCancel={onCancel} />)
    
    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
