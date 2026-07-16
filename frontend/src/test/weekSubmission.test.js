import { describe, expect, it } from 'vitest'
import { getWeekSubmissionBlockers } from '../features/operations/weekSubmission'

describe('getWeekSubmissionBlockers', () => {
  const now = new Date('2026-09-10T12:00:00')

  it('returns no blockers for completed or occurrence-backed past lessons', () => {
    expect(getWeekSubmissionBlockers([
      { date: '2026-09-09', timeslot: { end_time: '10:00:00' }, lesson_log_status: 'COMPLETED' },
      { date: '2026-09-09', timeslot: { end_time: '11:00:00' }, occurrence_status: 'GAP' },
    ], now)).toEqual([])
  })

  it('reports future and unregistered lessons from one pure result', () => {
    const blockers = getWeekSubmissionBlockers([
      {
        date: '2026-09-11',
        timeslot: { end_time: '10:00:00' },
        subject: { name: 'Matemática' },
      },
    ], now)

    expect(blockers).toHaveLength(1)
    expect(blockers[0]).toContain('Matemática')
    expect(blockers[0]).toContain('aula futura')
    expect(blockers[0]).toContain('não registada')
  })
})
