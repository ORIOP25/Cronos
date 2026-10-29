import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import TeacherAvailabilityModal from '../components/TeacherAvailabilityModal'
import { validatePresenceDraft } from '../components/TeacherPresenceSection'
import { renderWithProviders } from './testUtils'

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  savePresence: vi.fn(),
  timeslots: vi.fn(),
  availability: vi.fn(),
  presence: vi.fn(),
  presenceState: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: (options) => { mocks.timeslots(options); return {
    data: [{ id: 11, day_of_week: 0, start_time: '09:00', end_time: '09:50' }],
    isLoading: false,
    error: null,
  } },
}))

vi.mock('../features/operations/data', () => ({
  useTeacherAvailability: (options) => { mocks.availability(options); return {
    data: [{ timeslot_id: 11, score: 0 }],
    isLoading: false,
    error: null,
  } },
  useSaveTeacherAvailability: () => ({ mutateAsync: mocks.save, isPending: false }),
  useTeacherPresence: (options) => { mocks.presence(options); return mocks.presenceState() },
  useSaveTeacherPresence: () => ({ mutateAsync: mocks.savePresence, isPending: false }),
}))

const DEFAULT_PRESENCE = { lunch_required: true, minimum_hours: null, max_gap_hours: null }

describe('TeacherAvailabilityModal', () => {
  beforeEach(() => {
    mocks.save.mockReset()
    mocks.savePresence.mockReset()
    mocks.presenceState.mockReset().mockReturnValue({
      data: DEFAULT_PRESENCE,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
  })

  it('reads and saves the grid for the occurrence date', async () => {
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onDate="2031-01-01" onClose={vi.fn()} />, { withToaster: true })
    expect(mocks.timeslots).toHaveBeenLastCalledWith({ onDate: '2031-01-01' })
    expect(mocks.availability).toHaveBeenLastCalledWith({ teacherId: 7, onDate: '2031-01-01' })
    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({
      teacherId: 7, onDate: '2031-01-01', payload: [{ timeslot_id: 11, score: 1 }],
    }))
  })
  it('lets the direction edit availability without sending an invite', async () => {
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />, { withToaster: true })

    expect(screen.getByText('Disponibilidade — Prof. QA')).toBeInTheDocument()
    expect(screen.getByText(/Não envia convite/i)).toBeInTheDocument()

    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    expect(saveButton).toBeDisabled()

    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    await waitFor(() => expect(saveButton).toBeEnabled())

    fireEvent.click(saveButton)
    await waitFor(() => {
      expect(mocks.save).toHaveBeenCalledWith({
        teacherId: 7,
        payload: [{ timeslot_id: 11, score: 1 }],
      })
    })
    expect(await within(document.querySelector('[data-rht-toaster]')).findByText(/Disponibilidade guardada/i)).toBeInTheDocument()
  })

  it('keeps the presence section disabled until the saved rule loads (R24)', () => {
    mocks.presenceState.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    expect(mocks.presence).toHaveBeenLastCalledWith({ teacherId: 7 })
    expect(screen.getByText('Presença na escola')).toBeInTheDocument()
    expect(screen.getByText(/A carregar a regra de presença/)).toBeInTheDocument()
    expect(screen.getByLabelText('Mínimo de horas por presença')).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'Sim' })).toBeDisabled()
  })

  it('disables the presence section when the read fails', () => {
    mocks.presenceState.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    expect(screen.getByText('Não foi possível carregar a regra de presença.')).toBeInTheDocument()
    expect(screen.getByLabelText('Mínimo de horas por presença')).toBeDisabled()
  })

  it('loads the saved rule and saves only the dirty presence part', async () => {
    mocks.presenceState.mockReturnValue({
      data: { lunch_required: true, minimum_hours: 3, max_gap_hours: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    mocks.savePresence.mockResolvedValue({ lunch_required: false, minimum_hours: 3, max_gap_hours: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    expect(screen.getByText('Presença na escola')).toBeInTheDocument()
    expect(screen.getByLabelText('Mínimo de horas por presença')).toHaveValue(3)
    expect(screen.getByLabelText('Tempo máximo sem aulas por presença')).toHaveValue(1)
    expect(screen.getByText('Vale para todas as grelhas e anos letivos.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fechar', exact: true })).toBeEnabled()

    fireEvent.click(screen.getByRole('radio', { name: 'Não' }))
    expect(screen.getByRole('button', { name: 'Cancelar', exact: true })).toBeEnabled()
    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.savePresence).toHaveBeenCalledWith({
      teacherId: 7,
      payload: { lunch_required: false, minimum_hours: 3, max_gap_hours: 1 },
    }))
    expect(mocks.save).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Fechar', exact: true })).toBeEnabled()
  })

  it('defaults the gap to 1 when a minimum is set and clears it when the minimum is removed (R11)', async () => {
    mocks.savePresence.mockResolvedValue({ lunch_required: true, minimum_hours: 4, max_gap_hours: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    const minInput = screen.getByLabelText('Mínimo de horas por presença')
    expect(screen.queryByLabelText('Tempo máximo sem aulas por presença')).not.toBeInTheDocument()

    fireEvent.change(minInput, { target: { value: '4' } })
    expect(screen.getByLabelText('Tempo máximo sem aulas por presença')).toHaveValue(1)

    fireEvent.change(minInput, { target: { value: '' } })
    expect(screen.queryByLabelText('Tempo máximo sem aulas por presença')).not.toBeInTheDocument()

    fireEvent.change(minInput, { target: { value: '4' } })
    expect(screen.getByLabelText('Tempo máximo sem aulas por presença')).toHaveValue(1)

    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    await waitFor(() => expect(mocks.savePresence).toHaveBeenCalledWith({
      teacherId: 7,
      payload: { lunch_required: true, minimum_hours: 4, max_gap_hours: 1 },
    }))
  })

  it('shows the exact minimum and gap validation messages without sending the rule (T08)', async () => {
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    const minInput = screen.getByLabelText('Mínimo de horas por presença')
    fireEvent.change(minInput, { target: { value: '13' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))

    expect(await screen.findByText('O mínimo tem de estar entre 1 e 12 horas.')).toBeInTheDocument()
    expect(mocks.savePresence).not.toHaveBeenCalled()

    fireEvent.change(minInput, { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Tempo máximo sem aulas por presença'), { target: { value: '13' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))

    expect(await screen.findByText('O tempo máximo sem aulas tem de estar entre 0 e 12 horas.')).toBeInTheDocument()
    expect(mocks.savePresence).not.toHaveBeenCalled()
  })

  it('requires the minimum and gap together when only one is filled', () => {
    expect(validatePresenceDraft({ lunch_required: true, minimum_hours: 3, max_gap_hours: '' }))
      .toEqual({ max_gap_hours: 'Indique o mínimo de horas e o tempo máximo sem aulas, ou deixe os dois campos em branco.' })
    expect(validatePresenceDraft({ lunch_required: true, minimum_hours: '', max_gap_hours: 2 }))
      .toEqual({ max_gap_hours: 'Indique o mínimo de horas e o tempo máximo sem aulas, ou deixe os dois campos em branco.' })
    expect(validatePresenceDraft({ lunch_required: false, minimum_hours: 12, max_gap_hours: 0 })).toEqual({})
  })

  it('does not send a default presence while the rule is still loading (R24)', async () => {
    mocks.presenceState.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1))
    expect(mocks.savePresence).not.toHaveBeenCalled()
  })

  it('keeps the saved presence clean when the grid fails and names the grid (R23)', async () => {
    mocks.savePresence.mockResolvedValue({ lunch_required: false, minimum_hours: null, max_gap_hours: null })
    mocks.save.mockRejectedValueOnce({
      response: { status: 400, data: { detail: { code: 'bad_request', message: 'Pedido inválido.' } } },
    })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Não' }))

    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1))
    expect(mocks.savePresence).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('A presença ficou guardada. A grelha não foi guardada. Tente novamente.')).toBeInTheDocument()

    fireEvent.click(saveButton)
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2))
    expect(mocks.savePresence).toHaveBeenCalledTimes(1)
  })

  it('keeps the presence pending when only the grid saves', async () => {
    mocks.savePresence.mockRejectedValueOnce({
      response: { status: 400, data: { detail: { code: 'validation_error', message: 'x' } } },
    })
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Não' }))

    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.savePresence).toHaveBeenCalledTimes(1))
    expect(mocks.save).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('A presença não foi guardada. A grelha ficou guardada. Tente novamente.')).toBeInTheDocument()

    fireEvent.click(saveButton)
    await waitFor(() => expect(mocks.savePresence).toHaveBeenCalledTimes(2))
    expect(mocks.save).toHaveBeenCalledTimes(1)
  })

  it('connects the minimum input to its help and feedback text', async () => {
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    const minInput = screen.getByLabelText('Mínimo de horas por presença')
    expect(minInput).toHaveAttribute('aria-describedby', 'teacher-presence-minimum-hours-help')

    fireEvent.change(minInput, { target: { value: '13' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    await screen.findByText('O mínimo tem de estar entre 1 e 12 horas.')

    expect(screen.getByLabelText('Mínimo de horas por presença')).toHaveAttribute(
      'aria-describedby',
      'teacher-presence-minimum-hours-help teacher-presence-minimum-hours-feedback',
    )
  })

  it('connects the gap input to its feedback text', async () => {
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Mínimo de horas por presença'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Tempo máximo sem aulas por presença'), { target: { value: '13' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    await screen.findByText('O tempo máximo sem aulas tem de estar entre 0 e 12 horas.')

    expect(screen.getByLabelText('Tempo máximo sem aulas por presença')).toHaveAttribute(
      'aria-describedby',
      'teacher-presence-maximum-gap-feedback',
    )
  })

  it('keeps the edited presence draft when the rule refetches', async () => {
    const { rerender } = renderWithProviders(
      <TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('radio', { name: 'Não' }))
    expect(screen.getByRole('radio', { name: 'Não' })).toBeChecked()

    // A refetch returns a fresh object with the same saved values.
    mocks.presenceState.mockReturnValue({
      data: { lunch_required: true, minimum_hours: null, max_gap_hours: null },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    rerender(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    expect(screen.getByRole('radio', { name: 'Não' })).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: /guardar disponibilidade/i }))
    await waitFor(() => expect(mocks.savePresence).toHaveBeenCalledWith({
      teacherId: 7,
      payload: { lunch_required: false, minimum_hours: null, max_gap_hours: null },
    }))
  })

  it('still saves the grid when the presence read fails', async () => {
    mocks.presenceState.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() })
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    renderWithProviders(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

    fireEvent.pointerDown(screen.getByRole('button', { name: /Segunda, 09:00/i }))
    const saveButton = screen.getByRole('button', { name: /guardar disponibilidade/i })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1))
    expect(mocks.savePresence).not.toHaveBeenCalled()
  })
})
