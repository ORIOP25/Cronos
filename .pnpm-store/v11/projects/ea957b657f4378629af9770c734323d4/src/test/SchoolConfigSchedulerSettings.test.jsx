import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SchoolConfig from '../pages/SchoolConfig'
import { renderWithProviders } from './testUtils'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { withCredentials: true },
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

describe('SchoolConfig scheduler settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/settings/') {
        return Promise.resolve({ data: {
          school_start_date: '2026-09-15',
          school_hard_end_date: '2027-07-31',
          repair_stability_window_days: 14,
        } })
      }
      return Promise.resolve({ data: [] })
    })
    apiClient.post.mockResolvedValue({ data: {} })
  })

  it('submits hard boundaries and accepts a zero-day stability window', async () => {
    renderWithProviders(<SchoolConfig />)

    const repairWindow = await screen.findByLabelText(/janela de estabilidade/i)
    expect(screen.queryByLabelText(/fim previsto|data preferida/i)).not.toBeInTheDocument()

    fireEvent.change(repairWindow, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar configurações gerais/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar guarda/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/school/settings/', {
        school_start_date: '2026-09-15',
        school_hard_end_date: '2027-07-31',
        repair_stability_window_days: 0,
      })
    })
  })
})
