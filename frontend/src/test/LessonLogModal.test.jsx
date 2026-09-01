import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LessonLogModal from '../components/LessonLogModal'

const mutations = vi.hoisted(() => ({
  upsert: vi.fn(),
  updateStatus: vi.fn(),
}))

vi.mock('../features/operations/data', () => ({
  useUpsertLessonLog: () => ({ isPending: false, mutateAsync: mutations.upsert }),
  useUpdateTimesheetStatus: () => ({ isPending: false, mutateAsync: mutations.updateStatus }),
}))

describe('LessonLogModal permissions', () => {
  it('renders a submitted tutorial week as consultation-only', () => {
    render(
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
          active_schedule_block_id: 2,
          is_past: true,
        }}
      />,
    )

    expect(screen.getByText(/semana submetida — modo de consulta/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Sumário')).toBeDisabled()
    expect(screen.getByLabelText('Notas Opcionais')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guardar alterações' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reabrir Semana' })).not.toBeInTheDocument()
    expect(mutations.upsert).not.toHaveBeenCalled()
  })
})
