import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import SubjectForm from '../components/Forms/SubjectForm'

const defaultProps = {
  initialData: null,
  onSubmit: vi.fn(),
  isLoading: false,
  onCancel: vi.fn(),
}

describe('SubjectForm wizard', () => {
  it('renderiza passo 1 por defeito', () => {
    render(<SubjectForm {...defaultProps} />)
    expect(screen.getByText('1. Dados Gerais')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Matem/i)).toBeInTheDocument()
  })

  it('mostra indicador dos dois passos', () => {
    render(<SubjectForm {...defaultProps} />)
    expect(screen.getByText('1. Dados Gerais')).toBeInTheDocument()
    expect(screen.getByText(/2\./)).toBeInTheDocument()
  })

  it('avanca para modulos quando o nome esta preenchido', () => {
    render(<SubjectForm {...defaultProps} />)

    fireEvent.change(screen.getByPlaceholderText(/Matem/i), {
      target: { value: 'Programacao' },
    })
    fireEvent.click(screen.getByRole('button', { name: /proximo|pr.ximo/i }))

    expect(screen.getByText(/Adicionar M/i)).toBeInTheDocument()
  })

  it('nao avanca quando o nome tem apenas espacos', () => {
    render(<SubjectForm {...defaultProps} />)

    fireEvent.change(screen.getByPlaceholderText(/Matem/i), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /proximo|pr.ximo/i }))

    expect(screen.queryByText(/Adicionar M/i)).not.toBeInTheDocument()
  })

  it('mantem proximo desativado sem nome', () => {
    render(<SubjectForm {...defaultProps} />)
    expect(screen.getByRole('button', { name: /proximo|pr.ximo/i })).toBeDisabled()
  })

  it('mostra campos de modulo no passo 2', () => {
    render(<SubjectForm {...defaultProps} />)

    fireEvent.change(screen.getByPlaceholderText(/Matem/i), {
      target: { value: 'Fisica' },
    })
    fireEvent.click(screen.getByRole('button', { name: /proximo|pr.ximo/i }))

    expect(screen.getByPlaceholderText(/Geometria/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('001')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('H')).toBeInTheDocument()
  })

  it('submete payload limpo com modulos reordenados e horas numericas', () => {
    const onSubmit = vi.fn()
    render(<SubjectForm {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.change(screen.getByPlaceholderText(/Matem/i), {
      target: { value: ' Programacao ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /proximo|pr.ximo/i }))
    fireEvent.change(screen.getByPlaceholderText(/Geometria/i), {
      target: { value: ' Modulo 1 ' },
    })
    fireEvent.change(screen.getByPlaceholderText('001'), {
      target: { value: ' UFCD001 ' },
    })
    fireEvent.change(screen.getByPlaceholderText('H'), {
      target: { value: '25' },
    })
    fireEvent.click(screen.getByRole('button', { name: /adicionar/i }))
    fireEvent.click(screen.getByRole('button', { name: /guardar/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Programacao',
      required_room_type: 'normal',
      modules: [
        {
          name: 'Modulo 1',
          code: 'UFCD001',
          hours_total: 25,
          order: 0,
        },
      ],
    })
  })

  it('nao permite adicionar modulo com horas nao positivas', () => {
    render(<SubjectForm {...defaultProps} />)

    fireEvent.change(screen.getByPlaceholderText(/Matem/i), {
      target: { value: 'Fisica' },
    })
    fireEvent.click(screen.getByRole('button', { name: /proximo|pr.ximo/i }))
    fireEvent.change(screen.getByPlaceholderText(/Geometria/i), {
      target: { value: 'Modulo invalido' },
    })
    fireEvent.change(screen.getByPlaceholderText('H'), {
      target: { value: '0' },
    })

    expect(screen.getByRole('button', { name: /adicionar/i })).toBeDisabled()
  })

  it('dropdown de tipo de sala contem opcoes principais', () => {
    render(<SubjectForm {...defaultProps} />)
    const select = screen.getByRole('combobox')
    expect(select).toHaveValue('normal')
    expect([...select.options].map((option) => option.value)).toEqual(
      expect.arrayContaining(['normal', 'lab', 'gym', 'art'])
    )
  })

  it('popula campos na edicao', () => {
    render(
      <SubjectForm
        {...defaultProps}
        initialData={{
          name: 'Matematica',
          required_room_type: 'lab',
          modules: [{ id: 1, name: 'M1', code: 'P01', hours_total: 25, order: 0 }],
        }}
      />
    )

    expect(screen.getByDisplayValue('Matematica')).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('lab')
  })

  it('botao cancelar chama onCancel', () => {
    const onCancel = vi.fn()
    render(<SubjectForm {...defaultProps} onCancel={onCancel} />)

    fireEvent.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
