import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import MyAvailability from '../pages/MyAvailability'

vi.mock('../hooks/useSchoolData', () => ({
  useCurrentMember: () => ({
    data: { teacher_id: 42 },
    isLoading: false,
  }),
  useTimeslots: () => ({
    data: [
      { id: 1, day_of_week: 0, start_time: '08:00:00' },
      { id: 2, day_of_week: 1, start_time: '08:00:00' },
    ],
    isLoading: false,
  }),
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
})
