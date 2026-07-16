import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WeekNavigator from '../components/WeekNavigator'

describe('WeekNavigator', () => {
  it('shows the week and moves backward, forward, and to today', () => {
    const onChange = vi.fn()
    render(<WeekNavigator value="2026-05-04" onChange={onChange} />)
    expect(screen.getByText(/04.*08.*2026/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /semana anterior/i }))
    fireEvent.click(screen.getByRole('button', { name: /próxima semana/i }))
    fireEvent.click(screen.getByRole('button', { name: /hoje/i }))
    expect(onChange.mock.calls[0][0]).toBe('2026-04-27')
    expect(onChange.mock.calls[1][0]).toBe('2026-05-11')
    expect(onChange.mock.calls[2][0]).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
