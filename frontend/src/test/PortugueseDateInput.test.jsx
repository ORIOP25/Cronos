import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PortugueseDateInput from '../components/PortugueseDateInput'

describe('PortugueseDateInput', () => {
  it('opens a native calendar while keeping the Portuguese display format', () => {
    const onChange = vi.fn()
    const { container } = render(
      <PortugueseDateInput aria-label="Data" value="2026-09-15" onChange={onChange} />
    )
    const displayedInput = screen.getByRole('textbox', { name: 'Data' })
    const calendarInput = container.querySelector('input[type="date"]')
    const showPicker = vi.fn()
    calendarInput.showPicker = showPicker

    expect(displayedInput).toHaveValue('15/09/2026')

    fireEvent.click(displayedInput)
    expect(showPicker).toHaveBeenCalledOnce()

    fireEvent.change(calendarInput, { target: { value: '2026-09-20' } })
    expect(onChange).toHaveBeenCalledWith('2026-09-20')
  })
})
