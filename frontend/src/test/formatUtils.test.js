import { describe, it, expect } from 'vitest'
import {
  formatDate,
  formatDateTime,
  formatDateLong,
  formatDateShort,
  formatWeekRange,
  formatNumber,
  normalizeTimeLabel,
  getCurrentWeekMonday,
  addDays,
  toIsoDate,
  toWeekMonday,
  isAfterDate,
} from '../utils/formatUtils'

describe('formatUtils', () => {
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

  describe('formatNumber', () => {
    it('formata números com separador PT', () => {
      const result = formatNumber(1200)
      // toLocaleString('pt-PT') pode retornar '1 200' ou '1200' dependendo da ICU
      expect(typeof result).toBe('string')
      expect(result).toMatch(/1\s?200/)
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

  describe('toWeekMonday', () => {
    it('calcula a segunda-feira da semana', () => {
      // 2026-05-03 é domingo — a segunda anterior é 2026-04-27
      const monday = toWeekMonday(new Date(2026, 4, 3, 12, 0, 0))
      expect(monday).toBe('2026-04-27')
    })
  })
})
