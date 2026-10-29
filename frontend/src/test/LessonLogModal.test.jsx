import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LessonLogModal from '../components/LessonLogModal'
import { renderWithProviders } from './testUtils'

const mutations = vi.hoisted(() => ({
  upsert: vi.fn(),
  updateStatus: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useUpsertLessonLog: () => ({ isPending: false, mutateAsync: mutations.upsert }),
  useUpdateTimesheetStatus: () => ({ isPending: false, mutateAsync: mutations.updateStatus }),
}))

const pendingSlot = {
  date: '2025-09-16',
  lesson_log_status: 'PENDING',
  week_timesheet_status: 'OPEN',
  timeslot: { end_time: '09:00:00' },
  timesheet_id: 1,
  scheduler_lesson_id: 2,
  is_past: true,
}

describe('LessonLogModal permissions', () => {
  beforeEach(() => {
    mutations.upsert.mockReset()
    mutations.updateStatus.mockReset()
  })

  it('reports a transient save failure as a single toast and keeps the modal', async () => {
    mutations.upsert.mockRejectedValueOnce({ response: { status: 503, data: { detail: { code: 'service_unavailable' } } } })
    renderWithProviders(<LessonLogModal onClose={vi.fn()} slot={pendingSlot} />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: /aula dada/i }))

    const host = document.querySelector('[data-rht-toaster]')
    expect(await within(host).findByText(/tente novamente dentro de instantes/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /aula dada/i })).toBeEnabled()
    expect(screen.queryByText(/tente novamente dentro de instantes/i, { selector: '.alert' })).not.toBeInTheDocument()
  })

  it('keeps a server block in context without a toast', async () => {
    mutations.upsert.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'conflict' } } } })
    renderWithProviders(<LessonLogModal onClose={vi.fn()} slot={pendingSlot} />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: /aula dada/i }))

    expect(await screen.findByText(/atualize a página e tente novamente/i)).toBeInTheDocument()
    expect(document.querySelector('[data-rht-toaster]')).toBeEmptyDOMElement()
  })

  it('renders a submitted tutorial week as consultation-only', () => {    render(
      <LessonLogModal
        onClose={vi.fn()}
        isAdmin
        allowedActions={[]}
        referenceDate="2025-09-20T12:00:00Z"
        slot={{
          date: '2025-09-16',
          lesson_log_status: 'COMPLETED',
          lesson_log_summary: 'Aula concluída',
          lesson_log_notes: 'Notas da aula',
          week_timesheet_status: 'SUBMITTED',
          timeslot: { end_time: '09:00:00' },
          timesheet_id: 1,
          scheduler_lesson_id: 2,
          is_past: true,
        }}
      />,
    )

    expect(screen.getByText(/semana submetida — modo de consulta/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Sumário')).toBeDisabled()
    expect(screen.getByLabelText('Notas Opcionais')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guardar alterações' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reabrir semana' })).not.toBeInTheDocument()
    expect(mutations.upsert).not.toHaveBeenCalled()
  })

  it('shows the joint present classes and sends absent_class_ids', async () => {
    mutations.upsert.mockResolvedValueOnce({})
    renderWithProviders(
      <LessonLogModal
        onClose={vi.fn()}
        slot={{
          date: '2025-09-16',
          lesson_log_status: 'PENDING',
          week_timesheet_status: 'OPEN',
          timeslot: { end_time: '09:00:00' },
          timesheet_id: 1,
          scheduler_lesson_id: 2,
          is_past: true,
          class_infos: [
            { id: 11, name: '10.º MKT', lesson_log_status: 'COMPLETED', lesson_db_id: 101 },
            { id: 12, name: '10.º MAS', lesson_log_status: 'OCCURRENCE', lesson_db_id: 102 },
          ],
        }}
      />,
      { withToaster: true },
    )

    const mkt = screen.getByLabelText('10.º MKT')
    const mas = screen.getByLabelText('10.º MAS')
    expect(mkt).toBeChecked()
    expect(mas).not.toBeChecked()
    expect(screen.getByText(/ocorrência pendente/i)).toBeInTheDocument()

    // The last present class cannot be unchecked.
    fireEvent.click(mkt)
    expect(mkt).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: /aula dada/i }))

    await waitFor(() => expect(mutations.upsert).toHaveBeenCalledWith(expect.objectContaining({
      schedulerLessonId: 2,
      payload: expect.objectContaining({ status: 'COMPLETED', absent_class_ids: [12] }),
    })))
  })

  it('preserves the absent sibling when reopening a completed joint lesson', async () => {
    mutations.upsert.mockResolvedValueOnce({})
    renderWithProviders(
      <LessonLogModal
        onClose={vi.fn()}
        slot={{
          date: '2025-09-16',
          lesson_log_status: 'COMPLETED',
          week_timesheet_status: 'OPEN',
          timeslot: { end_time: '09:00:00' },
          timesheet_id: 1,
          scheduler_lesson_id: 2,
          is_past: true,
          class_infos: [
            { id: 11, name: '10.º MKT', lesson_log_status: 'COMPLETED', lesson_db_id: 101 },
            { id: 12, name: '10.º MAS', lesson_log_status: 'OCCURRENCE', lesson_db_id: 102 },
          ],
        }}
      />,
      { withToaster: true },
    )

    expect(screen.getByLabelText('10.º MKT')).toBeChecked()
    expect(screen.getByLabelText('10.º MAS')).not.toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: /guardar altera/i }))

    await waitFor(() => expect(mutations.upsert).toHaveBeenCalledWith(expect.objectContaining({
      payload: expect.objectContaining({ status: 'COMPLETED', absent_class_ids: [12] }),
    })))
  })
})
