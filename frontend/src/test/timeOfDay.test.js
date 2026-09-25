// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  formatTimeOfDay,
  normalizeTimeOfDay,
  parseTimeOfDay,
  timeOfDayToMinutes,
} from '../utils/timeOfDay'

describe('timeOfDay', () => {
  it('accepts 24h hours with or without a leading zero', () => {
    expect(parseTimeOfDay('8:30')).toEqual({ hours: 8, minutes: 30 })
    expect(parseTimeOfDay('08:30')).toEqual({ hours: 8, minutes: 30 })
    expect(parseTimeOfDay('0:00')).toEqual({ hours: 0, minutes: 0 })
    expect(parseTimeOfDay('23:59')).toEqual({ hours: 23, minutes: 59 })
  })

  it('accepts persisted values with zero seconds', () => {
    expect(normalizeTimeOfDay('08:30:00')).toBe('08:30')
    expect(formatTimeOfDay('08:30:00')).toBe('8:30')
  })

  it('normalizes to HH:mm for saving and formats H:mm for display', () => {
    expect(normalizeTimeOfDay('8:30')).toBe('08:30')
    expect(normalizeTimeOfDay('8:05')).toBe('08:05')
    expect(formatTimeOfDay('08:30')).toBe('8:30')
    expect(formatTimeOfDay('08:05')).toBe('8:05')
  })

  it('rejects AM/PM, incomplete minutes and out-of-range values', () => {
    expect(normalizeTimeOfDay('8:30 AM')).toBeNull()
    expect(normalizeTimeOfDay('8:3')).toBeNull()
    expect(normalizeTimeOfDay('24:00')).toBeNull()
    expect(normalizeTimeOfDay('12:60')).toBeNull()
    expect(normalizeTimeOfDay('8')).toBeNull()
    expect(normalizeTimeOfDay('08:30:15')).toBeNull()
    expect(normalizeTimeOfDay('')).toBeNull()
    expect(normalizeTimeOfDay(null)).toBeNull()
  })

  it('keeps an invalid draft visible while formatting', () => {
    expect(formatTimeOfDay('8:3')).toBe('8:3')
    expect(formatTimeOfDay('')).toBe('')
  })

  it('converts to minutes and rejects invalid values', () => {
    expect(timeOfDayToMinutes('8:30')).toBe(510)
    expect(timeOfDayToMinutes('08:30:00')).toBe(510)
    expect(Number.isNaN(timeOfDayToMinutes('8:3'))).toBe(true)
    expect(Number.isNaN(timeOfDayToMinutes(''))).toBe(true)
  })
})
