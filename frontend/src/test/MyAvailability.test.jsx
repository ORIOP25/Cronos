import { act } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import MyAvailability from '../pages/MyAvailability'

const toastHost = () => document.querySelector('[data-rht-toaster]')

const TIMESLOTS = [
  { id: 1, day_of_week: 0, start_time: '08:00:00' },
  { id: 2, day_of_week: 1, start_time: '08:00:00' },
  { id: 3, day_of_week: 0, start_time: '09:00:00' },
]

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  presence: vi.fn(),
  timeslots: { data: [], isLoading: false, error: null },
  availability: { data: [], isLoading: false, error: null },
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({
    data: { teacher_id: 42 },
    isLoading: false,
  }),
}))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => mocks.timeslots,
}))

vi.mock('../features/operations/data', () => ({
  useMyAvailability: () => mocks.availability,
  useMyPresence: () => mocks.presence(),
  useSaveAvailability: () => ({
    isPending: false,
    mutateAsync: mocks.save,
  }),
}))

const DEFAULT_PRESENCE = { lunch_required: true, minimum_hours: null, max_gap_hours: null }

describe('MyAvailability', () => {
  beforeEach(() => {
    mocks.save.mockReset()
    mocks.timeslots = { data: TIMESLOTS, isLoading: false, error: null }
    mocks.availability = { data: [{ timeslot_id: 1, score: 2 }], isLoading: false, error: null }
    mocks.presence.mockReset().mockReturnValue({
      data: DEFAULT_PRESENCE,
      isLoading: false,
      isError: false,
    })
    resetClerkState()
  })

  afterEach(() => {
    resetClerkState()
  })

  it('renders the availability page with the unified title and grid name', () => {
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: 'Minha disponibilidade' })).toBeVisible()
    expect(screen.getByRole('region', { name: 'Grelha de disponibilidade' })).toBeInTheDocument()
    expect(screen.queryByText(/Algo correu mal|Ocorreu um erro inesperado/i)).not.toBeInTheDocument()
  })

  it('shows the loading state with the availability title', () => {
    mocks.timeslots = { data: [], isLoading: true, error: null }
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: 'Minha disponibilidade' })).toBeVisible()
    expect(screen.getByText('A carregar disponibilidade')).toBeInTheDocument()
  })

  it('shows the permission error with the availability title', () => {
    mocks.availability = { data: [], isLoading: false, error: { response: { status: 403 } } }
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: 'Minha disponibilidade' })).toBeVisible()
    expect(screen.getByText('Sem permissões para consultar a disponibilidade.')).toBeInTheDocument()
  })

  it('shows the load failure with the availability title', () => {
    mocks.availability = { data: [], isLoading: false, error: { response: { status: 500 } } }
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: 'Minha disponibilidade' })).toBeVisible()
    expect(screen.getByText('Não foi possível carregar a disponibilidade. Tente novamente.')).toBeInTheDocument()
  })

  it('shows the empty grid with the availability text', () => {
    mocks.timeslots = { data: [], isLoading: false, error: null }
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('heading', { name: 'Minha disponibilidade' })).toBeVisible()
    expect(screen.getByText('A disponibilidade aparece depois de configurar a grelha horária.')).toBeInTheDocument()
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

  it('hides an empty block behind an accessible label instead of a bare dash', () => {
    renderWithProviders(<MyAvailability />)

    const emptyLabel = screen.getByText('Sem bloco')
    expect(emptyLabel).toHaveClass('visually-hidden')
    expect(emptyLabel.parentElement).toHaveClass('availability-grid__empty')
    expect(within(emptyLabel.parentElement).getByText('—')).toHaveAttribute('aria-hidden', 'true')
  })

  it('confirms a saved draft with a toast and clears the pending changes', async () => {
    mocks.save.mockResolvedValue(undefined)
    renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))

    expect(await within(toastHost()).findByText('Disponibilidade guardada.')).toBeInTheDocument()
    expect(screen.getByText(/0 blocos alterados/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar disponibilidade/i })).toBeDisabled()
  })

  it('ignores a save that resolves after the organization changed and keeps the new draft', async () => {
    let resolveSave
    mocks.save.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))
    setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
    const { rerender } = renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    act(() => { setClerkState({ orgId: 2 }) })
    rerender(<MyAvailability />)

    await act(async () => { resolveSave() })

    expect(screen.queryByText('Disponibilidade guardada.')).not.toBeInTheDocument()
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()

    mocks.save.mockImplementation(() => Promise.resolve())
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))

    expect(await within(toastHost()).findByText('Disponibilidade guardada.')).toBeInTheDocument()
    expect(screen.getByText(/0 blocos alterados/i)).toBeInTheDocument()
  })

  it('keeps the draft and a retry available when saving fails', async () => {
    mocks.save.mockRejectedValue({ response: { status: 500 } })
    renderWithProviders(<MyAvailability />, { withToaster: true })

    fireEvent.keyDown(screen.getByRole('button', { name: /segunda, 08:00/i }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))

    expect(await within(toastHost()).findByText('Não foi possível guardar a disponibilidade. Tente novamente.')).toBeInTheDocument()
    expect(screen.getByText(/1 bloco alterado/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /segunda, 08:00/i })).toHaveAccessibleName(/Neutro/)
    expect(screen.getByRole('button', { name: /guardar disponibilidade/i })).toBeEnabled()
  })

  it('hides the presence card for the default rule', () => {
    renderWithProviders(<MyAvailability />)

    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('shows the direction rule as read-only text when lunch is dispensed and a minimum is set', () => {
    mocks.presence.mockReturnValue({
      data: { lunch_required: false, minimum_hours: 3, max_gap_hours: 1 },
      isLoading: false,
      isError: false,
    })
    renderWithProviders(<MyAvailability />)

    const card = screen.getByRole('note', { name: /regra de presença/i })
    expect(card).toHaveTextContent(
      'A direção definiu: hora de almoço dispensada; mínimo de 3 horas por presença; tempo máximo sem aulas de 1 hora.',
    )
    expect(within(card).queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(within(card).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(card).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows lunch obrigatória when the rule keeps lunch and sets a minimum', () => {
    mocks.presence.mockReturnValue({
      data: { lunch_required: true, minimum_hours: 4, max_gap_hours: 2 },
      isLoading: false,
      isError: false,
    })
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('note', { name: /regra de presença/i })).toHaveTextContent(
      'A direção definiu: hora de almoço obrigatória; mínimo de 4 horas por presença; tempo máximo sem aulas de 2 horas.',
    )
  })

  it('uses the singular for one hour', () => {
    mocks.presence.mockReturnValue({
      data: { lunch_required: true, minimum_hours: 1, max_gap_hours: 1 },
      isLoading: false,
      isError: false,
    })
    renderWithProviders(<MyAvailability />)

    expect(screen.getByRole('note', { name: /regra de presença/i })).toHaveTextContent(
      'A direção definiu: hora de almoço obrigatória; mínimo de 1 hora por presença; tempo máximo sem aulas de 1 hora.',
    )
  })
})
