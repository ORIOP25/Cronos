import { describe, expect, it } from 'vitest'
import { formatGradeLevel, getRoomType, getTimesheetStatus } from '../utils/presentation'

describe('presentation metadata', () => {
  it('describes known and unknown room types', () => {
    expect(getRoomType('lab')).toEqual({ label: 'Laboratório', color: 'info' })
    expect(getRoomType('studio')).toEqual({ label: 'studio', color: 'secondary' })
  })

  it('formats grade levels and timesheet status fallbacks', () => {
    expect(formatGradeLevel(10)).toBe('10.º ano')
    expect(formatGradeLevel(null)).toBe('—')
    expect(getTimesheetStatus('APPROVED')).toMatchObject({ label: 'Aprovada', color: 'success' })
    expect(getTimesheetStatus('UNKNOWN')).toMatchObject({ label: 'UNKNOWN', color: 'secondary' })
  })
})
