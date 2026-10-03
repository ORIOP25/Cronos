import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import TeacherAvailabilityModal from '../components/TeacherAvailabilityModal'
import { renderWithProviders } from './testUtils'

const mocks = vi.hoisted(() => ({ save: vi.fn() }))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => ({
    data: [{ id: 11, day_of_week: 0, start_time: '09:00', end_time: '09:50' }],
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../features/operations/data', () => ({
  useTeacherAvailability: () => ({
    data: [{ timeslot_id: 11, score: 0 }],
    isLoading: false,
    error: null,
  }),
  useSaveTeacherAvailability: () => ({ mutateAsync: mocks.save, isPending: false }),
}))

describe('TeacherAvailabilityModal', () => {
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
})
