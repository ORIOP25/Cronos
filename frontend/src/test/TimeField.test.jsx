import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TimeField } from '../components/TimeField'

describe('TimeField', () => {
  it('renders an accessible 24h text field with a visual hour suffix', () => {
    render(
      <TimeField
        id="opening_time"
        label="Hora de Abertura"
        value="08:30:00"
        onChange={vi.fn()}
      />,
    )

    const input = screen.getByLabelText('Hora de Abertura')
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveAttribute('inputmode', 'numeric')
    expect(input).toHaveValue('8:30')
    const suffix = document.getElementById('opening_time-unit')
    expect(suffix).toHaveTextContent('h')
    expect(input).toHaveAttribute('aria-describedby', expect.stringContaining('opening_time-unit'))
    expect(input.value).not.toContain('h')
  })

  it('keeps an incomplete draft visible and reports the error', () => {
    render(
      <TimeField
        id="opening_time"
        label="Hora de Abertura"
        value="8:3"
        error="Hora inválida"
        onChange={vi.fn()}
      />,
    )

    const input = screen.getByLabelText('Hora de Abertura')
    expect(input).toHaveValue('8:3')
    expect(input).toHaveClass('is-invalid')
    expect(screen.getByText('Hora inválida')).toBeInTheDocument()
  })

  it('emits the raw text on change', () => {
    const onChange = vi.fn()
    render(
      <TimeField id="opening_time" label="Hora de Abertura" value="8:30" onChange={onChange} />,
    )

    fireEvent.change(screen.getByLabelText('Hora de Abertura'), { target: { value: '8:3' } })

    expect(onChange).toHaveBeenCalledWith('8:3')
  })
})
