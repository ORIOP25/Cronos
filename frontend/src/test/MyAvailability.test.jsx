import { act } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import MyAvailability from '../pages/MyAvailability'

const toastHost = () => document.querySelector('[data-rht-toaster]')

const operations = vi.hoisted(() => ({ save: vi.fn() }))

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
    mutateAsync: operations.save,
  }),
}))

describe('MyAvailability', () => {
  beforeEach(() => {
    operations.save.mockReset()
    resetClerkState()
  })

  afterEach(() => {
    resetClerkState()
  })

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

  it('confirms a saved draft with a toast and clears the pending changes', async () => {
    operations.save.mockResolvedValue(undefined)
    renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /guardar preferências/i }))

    expect(await within(toastHost()).findByText('Preferências guardadas.')).toBeInTheDocument()
    expect(screen.getByText(/0 blocos alterados/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar preferências/i })).toBeDisabled()
  })

  it('ignores a save that resolves after the organization changed and keeps the new draft', async () => {
    let resolveSave
    operations.save.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))
    setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
    const { rerender } = renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: /guardar preferências/i }))
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    act(() => { setClerkState({ orgId: 2 }) })
    rerender(<MyAvailability />)

    await act(async () => { resolveSave() })

    expect(screen.queryByText('Preferências guardadas.')).not.toBeInTheDocument()
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    operations.save.mockImplementation(() => Promise.resolve())
    fireEvent.click(screen.getByRole('button', { name: /guardar preferências/i }))

    expect(await within(toastHost()).findByText('Preferências guardadas.')).toBeInTheDocument()
    expect(screen.getByText(/0 blocos alterados/i)).toBeInTheDocument()
  })

  it('keeps the draft and a retry available when saving fails', async () => {
    operations.save.mockRejectedValue({ response: { status: 500 } })
    renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: /guardar preferências/i }))

    expect(await within(toastHost()).findByText('Erro ao gravar disponibilidade. Tente novamente.')).toBeInTheDocument()
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /segunda, 08:00/i })).toHaveAccessibleName(/Neutro/)
    expect(screen.getByRole('button', { name: /guardar preferências/i })).toBeEnabled()
  })
})
