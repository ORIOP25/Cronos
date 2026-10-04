import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import TeacherAvailabilityModal from '../components/TeacherAvailabilityModal'

const mocks = vi.hoisted(() => ({ save: vi.fn(), timeslots: vi.fn(), availability: vi.fn() }))

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
}))

describe('TeacherAvailabilityModal', () => {
  it('reads and saves the grid for the occurrence date', async () => {
    mocks.save.mockResolvedValue({ status: 'success', count: 1 })
    render(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onDate="2031-01-01" onClose={vi.fn()} />)
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
    render(<TeacherAvailabilityModal teacher={{ id: 7, name: 'Prof. QA' }} onClose={vi.fn()} />)

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
    expect(await screen.findByText(/Disponibilidade guardada/i)).toBeInTheDocument()
  })
})
