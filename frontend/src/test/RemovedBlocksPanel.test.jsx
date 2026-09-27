import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RemovedBlocksPanel from '../components/RemovedBlocksPanel'

describe('RemovedBlocksPanel', () => {
  it('shows an empty state when the week has no removed lessons', () => {
    render(<RemovedBlocksPanel blocks={[]} />)

    expect(screen.getByText(/sem aulas retiradas nesta semana/i)).toBeInTheDocument()
  })

  it('lists removed lessons with their preserved records', () => {
    render(
      <RemovedBlocksPanel
        blocks={[
          {
            id: 9,
            class_id: 1,
            class_name: '10A',
            subject_id: 2,
            subject_name: 'Matemática',
            teacher_id: 3,
            teacher_name: 'Prof. Ana',
            room_id: 4,
            room_name: 'Sala 1',
            date: '2026-02-02',
            timeslot_id: 1,
            start_time: '09:00:00',
            duration_minutes: 60,
            status: 'REMOVED',
            schedule_version_id: 'draft-1',
            updated_at: '2026-02-01T10:00:00Z',
            occurrence_status: 'GAP',
            lesson_log_status: null,
            lesson_log_summary: null,
          },
          {
            id: 10,
            class_id: 1,
            class_name: '10A',
            subject_id: 2,
            subject_name: 'Português',
            teacher_id: 3,
            teacher_name: 'Prof. Ana',
            room_id: 4,
            room_name: 'Sala 1',
            date: '2026-02-03',
            timeslot_id: 1,
            start_time: '10:00:00',
            duration_minutes: 60,
            status: 'REMOVED',
            schedule_version_id: 'draft-1',
            updated_at: '2026-02-01T10:00:00Z',
            occurrence_status: null,
            lesson_log_status: 'OCCURRENCE',
            lesson_log_summary: 'Sumário preservado',
          },
        ]}
      />,
    )

    expect(screen.getByText('02/02/2026')).toBeInTheDocument()
    expect(screen.getByText('09:00')).toBeInTheDocument()
    expect(screen.getByText('Matemática')).toBeInTheDocument()
    expect(screen.getAllByText('Prof. Ana')).toHaveLength(2)
    expect(screen.getByText('Falta registada')).toBeInTheDocument()
    expect(screen.getByText('Ocorrência registada')).toBeInTheDocument()
    expect(screen.getByText('Sumário preservado')).toBeInTheDocument()
  })
})
