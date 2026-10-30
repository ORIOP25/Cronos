import { describe, expect, it } from 'vitest'

import { classDebtRanking, classesBehind, debtSeries, expectedPercentage, pulseSummary } from '../features/dashboard/insights'

const week = (week_start, values = {}) => ({
  week_start, lessons_due: 0, lessons_given: 0, absence_minutes: 0, substituted_minutes: 0, missing_logs: 0, ...values,
})

describe('dashboard insights', () => {
  it('summarises the current week against the previous week and the year', () => {
    const summary = pulseSummary([
      week('2026-10-12', { lessons_due: 10, lessons_given: 8, absence_minutes: 120, substituted_minutes: 60, missing_logs: 1 }),
      week('2026-10-19', { lessons_due: 20, lessons_given: 19, absence_minutes: 60, substituted_minutes: 60, missing_logs: 2 }),
    ])

    expect(summary.current.week_start).toBe('2026-10-19')
    expect(summary.givenRate).toBe(95)
    expect(summary.previousGivenRate).toBe(80)
    expect(summary.coverageRate).toBe(100)
    expect(summary.yearCoverageRate).toBe(67)
    expect(summary.previous.absence_minutes).toBe(120)
    expect(summary.yearMissingLogs).toBe(3)
  })

  it('leaves rates empty when nothing was due', () => {
    const summary = pulseSummary([week('2026-10-19')])
    expect(summary.givenRate).toBeNull()
    expect(summary.previousGivenRate).toBeNull()
    expect(summary.coverageRate).toBeNull()
    expect(pulseSummary([]).current).toBeNull()
  })

  it('sums the debt of the selected classes per week', () => {
    const weeks = [
      { week_start: '2026-10-12', minutes_by_class: { 1: 60, 2: 30 } },
      { week_start: '2026-10-19', minutes_by_class: { 2: 90, 3: 10 } },
    ]
    expect(debtSeries(weeks, null)).toEqual([
      { week_start: '2026-10-12', minutes: 90 },
      { week_start: '2026-10-19', minutes: 100 },
    ])
    expect(debtSeries(weeks, new Set([2]))).toEqual([
      { week_start: '2026-10-12', minutes: 30 },
      { week_start: '2026-10-19', minutes: 90 },
    ])
  })

  it('compares each class progress with the share of lessons already planned', () => {
    const progress = [
      { class_id: 1, class_name: 'A', overall_percentage: 20, total_hours: 100 },
      { class_id: 2, class_name: 'B', overall_percentage: 50, total_hours: 100 },
      { class_id: 3, class_name: 'C', overall_percentage: 0, total_hours: 0 },
    ]
    const planned = { 1: 3000, 2: 2400 }

    expect(expectedPercentage(progress[0], planned)).toBe(50)
    expect(expectedPercentage(progress[2], planned)).toBeNull()
    expect(classesBehind(progress, planned)).toEqual([
      expect.objectContaining({ class_id: 1, expected: 50, behind: 30 }),
    ])
  })

  it('ranks classes by their debt in the latest week', () => {
    const weeks = [{ week_start: '2026-10-19', minutes_by_class: { 1: 30, 2: 90, 9: 400 } }]
    const progress = [{ class_id: 1, class_name: 'A' }, { class_id: 2, class_name: 'B' }]

    expect(classDebtRanking(weeks, progress)).toEqual([
      { class_id: 2, class_name: 'B', minutes: 90 },
      { class_id: 1, class_name: 'A', minutes: 30 },
    ])
    expect(classDebtRanking([], progress)).toEqual([])
  })
})
