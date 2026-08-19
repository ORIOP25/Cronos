import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import MyAvailability from '../pages/MyAvailability'

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({
    data: { teacher_id: 42 },
    isLoading: false,
  }),
}))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => ({
    data: [
      { id: 1, day_of_week: 0, start_time: '08:00:00' },
      { id: 2, day_of_week: 1, start_time: '08:00:00' },
    ],
    isLoading: false,
  }),
}))

vi.mock('../features/operations/data', () => ({
  useMyAvailability: () => ({
    data: [
      { timeslot_id: 1, score: 2 },
    ],
    isLoading: false,
  }),
  useSaveAvailability: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
}))

describe('MyAvailability', () => {
  it('renders teacher availability preferences without crashing', () => {
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: /Minhas Preferencias|Minhas Preferências/i })).toBeVisible()
    expect(screen.queryByText(/Algo correu mal|Ocorreu um erro inesperado/i)).not.toBeInTheDocument()
  })

  it('orders the painting tools by intent and does not pre-highlight the first slot', () => {
    renderWithProviders(<MyAvailability />)

    const toolbar = screen.getByRole('toolbar', { name: /ferramentas de disponibilidade/i })
    expect(within(toolbar).getAllByRole('button').map((button) => button.textContent.trim())).toEqual([
      'Preferencial',
      'Neutro',
      'Evitar',
      'Impossível',
    ])

    const firstSlot = screen.getByRole('button', { name: /segunda, 08:00/i })
    expect(firstSlot).not.toHaveClass('is-focused')
  })
})
