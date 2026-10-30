// @vitest-environment node
import { describe, it, expect } from 'vitest'
import {
  TXT,
  humanizeOperationalDetail,
  EVENT_TYPE_LABELS,
  OPERATIONAL_STATE_LABELS,
} from '../utils/terminology'

describe('terminology', () => {
  describe('TXT', () => {
    it('todas as chaves têm valores em PT-PT', () => {
      for (const [, value] of Object.entries(TXT)) {
        expect(typeof value).toBe('string')
        expect(value.trim()).not.toBe('')
        // Verifica que não contém palavras isoladas em inglês (word boundary)
        expect(value).not.toMatch(/\bSave\b/)
        expect(value).not.toMatch(/\bDelete\b/)
        expect(value).not.toMatch(/\bEdit\b/)
      }
    })
  })

  describe('humanizeOperationalDetail', () => {
    it('traduz CP-SAT para "gerador de horários"', () => {
      expect(humanizeOperationalDetail('Erro no CP-SAT')).toContain('gerador de horários')
      expect(humanizeOperationalDetail('CP-SAT failed')).toContain('gerador de horários')
    })

    it('traduz solver para "gerador de horários"', () => {
      expect(humanizeOperationalDetail('solver error')).toContain('gerador de horários')
    })

    it('traduz worker para "serviço de geração"', () => {
      expect(humanizeOperationalDetail('worker timeout')).toContain('serviço de geração')
    })

    it('retorna o valor original se não houver termos técnicos', () => {
      expect(humanizeOperationalDetail('Erro genérico')).toBe('Erro genérico')
    })

    it('retorna o valor original para strings vazias', () => {
      expect(humanizeOperationalDetail('')).toBe('')
      expect(humanizeOperationalDetail(null)).toBe(null)
      expect(humanizeOperationalDetail(undefined)).toBe(undefined)
    })
  })

  describe('EVENT_TYPE_LABELS', () => {
    it('tem todas as chaves de tipo de evento', () => {
      expect(EVENT_TYPE_LABELS.national_holiday).toBe('Feriado nacional')
      expect(EVENT_TYPE_LABELS.school_break).toBe('Pausa escolar')
      expect(EVENT_TYPE_LABELS.exam_period).toBe('Período de exames')
      expect(EVENT_TYPE_LABELS.other).toBe('Outro')
    })
  })

  it('does not expose corrupted UTF-8 text in shared labels', () => {
    const sharedLabels = [
      ...Object.values(TXT),
      ...Object.values(EVENT_TYPE_LABELS),
      ...Object.values(OPERATIONAL_STATE_LABELS),
    ]

    sharedLabels.forEach((label) => {
      expect(label).not.toMatch(/\u00C3[\u0080-\u00BF]|\u00C2[\u0080-\u00BF]|\u00E2\u20AC/)
    })
  })
})
