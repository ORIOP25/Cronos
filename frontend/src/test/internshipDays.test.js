import { describe, expect, it } from 'vitest'
import { collectInternshipDays } from '../utils/internshipDays'

const FLOW = {
  id: 1,
  event_type: 'internship_flow',
  start_date: '2026-02-02',
  end_date: '2026-02-04',
  class_ids: [10],
  applies_to_current_school_year: true,
}

describe('collectInternshipDays', () => {
  it('collects the flow days inside the week for the selected class', () => {
    expect(collectInternshipDays([FLOW], 10, '2026-02-02', '2026-02-08')).toEqual([
      '2026-02-02',
      '2026-02-03',
      '2026-02-04',
    ])
    expect(collectInternshipDays([FLOW], 10, '2026-02-05', '2026-02-08')).toEqual([])
  })

  it('ignores other classes, other event types, and previous-year flows', () => {
    expect(collectInternshipDays([FLOW], 11, '2026-02-02', '2026-02-08')).toEqual([])
    expect(
      collectInternshipDays([{ ...FLOW, event_type: 'school_break' }], 10, '2026-02-02', '2026-02-08'),
    ).toEqual([])
    expect(
      collectInternshipDays(
        [{ ...FLOW, applies_to_current_school_year: false }],
        10,
        '2026-02-02',
        '2026-02-08',
      ),
    ).toEqual([])
  })

  it('requires a class and a week range', () => {
    expect(collectInternshipDays([FLOW], null, '2026-02-02', '2026-02-08')).toEqual([])
    expect(collectInternshipDays([FLOW], 10, '', '')).toEqual([])
  })
})
