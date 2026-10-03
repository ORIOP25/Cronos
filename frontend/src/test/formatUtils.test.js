// @vitest-environment node
import { describe, it, expect } from 'vitest'
import {
  formatDate,
  formatDateTime,
  formatDateLong,
  formatDateShort,
  formatDateInput,
  parseDateInput,
  formatWeekRange,
  normalizeTimeLabel,
  getCurrentWeekMonday,
  addDays,
  toIsoDate,
  toWeekMonday,
  isAfterDate,
  formatDurationHours,
  formatDurationMinutes,
} from '../utils/formatUtils'

describe('formatUtils', () => {
  describe('date input format', () => {
    it('formats ISO dates for Portuguese date fields', () => {
      expect(formatDateInput('2026-05-03')).toBe('03/05/2026')
      expect(formatDateInput('')).toBe('')
    })

    it('parses Portuguese dates while preserving the ISO API contract', () => {
      expect(parseDateInput('03/05/2026')).toBe('2026-05-03')
      expect(parseDateInput('2026-05-03')).toBe('2026-05-03')
      expect(parseDateInput('31/02/2026')).toBeNull()
      expect(parseDateInput('')).toBe('')
    })
  })

  describe('formatDate', () => {
    it('formata data ISO para DD/MM/AAAA', () => {
      expect(formatDate('2026-05-03')).toBe('03/05/2026')
    })

    it('retorna "—" para null/undefined/vazio', () => {
      expect(formatDate(null)).toBe('—')
      expect(formatDate(undefined)).toBe('—')
      expect(formatDate('')).toBe('—')
    })

    it('retorna o valor original se a data for inválida', () => {
      expect(formatDate('not-a-date')).toBe('not-a-date')
    })
  })

  describe('formatDateTime', () => {
    it('formata timestamp ISO para DD/MM/AAAA, HH:MM', () => {
      const result = formatDateTime('2026-05-03T14:30:00')
      expect(result).toContain('03/05/2026')
      expect(result).toContain('14:30')
    })

    it('retorna "—" para null/undefined/vazio', () => {
      expect(formatDateTime(null)).toBe('—')
      expect(formatDateTime('')).toBe('—')
    })
  })

  describe('formatDateLong', () => {
    it('formata com mês por extenso', () => {
      const result = formatDateLong('2026-05-03')
      expect(result).toContain('maio')
      expect(result).toContain('2026')
    })
  })

  describe('formatDateShort', () => {
    it('formata dia + mês abreviado', () => {
      const result = formatDateShort('2026-05-03')
      // O output pode ser '03/mai' ou '03/05' dependendo da ICU do sistema
      expect(result).toMatch(/^\d{2}\//)
    })
  })

  describe('formatWeekRange', () => {
    it('formata intervalo de segunda a sexta', () => {
      const result = formatWeekRange('2026-05-04')
      expect(result).toContain('–')
      // Verifica que contém duas datas separadas
      expect(result.split('–').length).toBe(2)
    })
  })

  describe('normalizeTimeLabel', () => {
    it('trunca hora para HH:MM', () => {
      expect(normalizeTimeLabel('08:30:00')).toBe('08:30')
      expect(normalizeTimeLabel('08:30')).toBe('08:30')
    })

    it('retorna "" para valores vazios', () => {
      expect(normalizeTimeLabel(null)).toBe('')
      expect(normalizeTimeLabel('')).toBe('')
    })
  })

  describe('getCurrentWeekMonday', () => {
    it('retorna uma string ISO de segunda-feira', () => {
      const monday = getCurrentWeekMonday()
      expect(monday).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })
  })

  describe('addDays', () => {
    it('adiciona dias corretamente', () => {
      expect(addDays('2026-05-01', 7)).toBe('2026-05-08')
      expect(addDays('2026-05-01', -1)).toBe('2026-04-30')
    })

    it('uses local calendar arithmetic across Lisbon DST boundaries', () => {
      expect(addDays('2026-03-28', 1)).toBe('2026-03-29')
      expect(addDays('2026-10-24', 1)).toBe('2026-10-25')
    })

    it('accepts Date values and rejects malformed input', () => {
      expect(addDays(new Date(2026, 4, 1), 1)).toBe('2026-05-02')
      expect(addDays('2026-02-30', 1)).toBe('')
      expect(addDays('bad-value', 1)).toBe('')
    })
  })

  describe('toIsoDate', () => {
    it('converte Date para string ISO', () => {
      const d = new Date(2026, 4, 3, 12, 0, 0) // Maio = 4
      expect(toIsoDate(d)).toBe('2026-05-03')
    })
  })

  describe('isAfterDate', () => {
    it('compara datas corretamente', () => {
      expect(isAfterDate('2026-05-10', '2026-05-01')).toBe(true)
      expect(isAfterDate('2026-05-01', '2026-05-10')).toBe(false)
      expect(isAfterDate('2026-05-01', '2026-05-01')).toBe(false)
    })
  })

  describe('formatDuration', () => {
    it('presents internal decimals as Portuguese durations', () => {
      expect(formatDurationHours(0.8333333333333334)).toBe('50 min')
      expect(formatDurationHours(1.6666666666666667)).toBe('1 h 40 min')
      expect(formatDurationHours(2)).toBe('2 h')
      expect(formatDurationHours(0)).toBe('0 min')
    })

    it('formats minutes directly and tolerates missing values', () => {
      expect(formatDurationMinutes(50)).toBe('50 min')
      expect(formatDurationMinutes(100)).toBe('1 h 40 min')
      expect(formatDurationMinutes(null)).toBe('0 min')
      expect(formatDurationMinutes('bad')).toBe('0 min')
    })
  })

  describe('toWeekMonday', () => {
    it('calcula a segunda-feira da semana', () => {
      // 2026-05-03 é domingo — a segunda anterior é 2026-04-27
      const monday = toWeekMonday(new Date(2026, 4, 3, 12, 0, 0))
      expect(monday).toBe('2026-04-27')
    })

    it('handles Sunday strings and malformed input', () => {
      expect(toWeekMonday('2026-05-03')).toBe('2026-04-27')
      expect(toWeekMonday('not-a-date')).toBe('')
      expect(toWeekMonday(new Date('invalid'))).toBe('')
    })
  })
})
