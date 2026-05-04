import { describe, it, expect } from 'vitest'
import { TXT, humanizeOperationalDetail, EVENT_TYPE_LABELS } from '../utils/terminology'

describe('terminology', () => {
  describe('TXT', () => {
    it('contém todas as chaves de ação', () => {
      expect(TXT.SAVE).toBe('Guardar')
      expect(TXT.CANCEL).toBe('Cancelar')
      expect(TXT.REMOVE).toBe('Remover')
      expect(TXT.EDIT).toBe('Editar')
      expect(TXT.CREATE).toBe('Criar')
      expect(TXT.ADD).toBe('Adicionar')
      expect(TXT.CONFIRM).toBe('Confirmar')
    })

    it('contém chaves de estado', () => {
      expect(TXT.LOADING).toBe('A carregar…')
      expect(TXT.EMPTY_TABLE).toBe('Ainda sem registos.')
      expect(TXT.ERROR_LOADING).toBeTruthy()
    })

    it('contém chaves de ocorrência', () => {
      expect(TXT.OCCURRENCE_GIVEN).toBe('Dada')
      expect(TXT.OCCURRENCE_GAP).toBe('Furo')
      expect(TXT.OCCURRENCE_SUBSTITUTED).toBe('Substituída')
      expect(TXT.OCCURRENCE_PENDING_DECISION).toBe('Pendente de decisão')
    })

    it('todas as chaves têm valores em PT-PT', () => {
      for (const [key, value] of Object.entries(TXT)) {
        expect(value).toBeTruthy()
        expect(typeof value).toBe('string')
        // Verifica que não contém palavras isoladas em inglês (word boundary)
        expect(value).not.toMatch(/\bSave\b/)
        expect(value).not.toMatch(/\bDelete\b/)
        expect(value).not.toMatch(/\bEdit\b/)
      }
    })
  })

  describe('humanizeOperationalDetail', () => {
    it('traduz CP-SAT para "motor de cálculo"', () => {
      expect(humanizeOperationalDetail('Erro no CP-SAT')).toContain('motor de cálculo')
      expect(humanizeOperationalDetail('CP-SAT failed')).toContain('motor de cálculo')
    })

    it('traduz solver para "motor de cálculo"', () => {
      expect(humanizeOperationalDetail('solver error')).toContain('motor de cálculo')
    })

    it('traduz worker para "servidor de processamento"', () => {
      expect(humanizeOperationalDetail('worker timeout')).toContain('servidor de processamento')
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
      expect(EVENT_TYPE_LABELS.national_holiday).toBe('Feriado Nacional')
      expect(EVENT_TYPE_LABELS.school_break).toBe('Pausa Escolar')
      expect(EVENT_TYPE_LABELS.exam_period).toBe('Período de Exames')
      expect(EVENT_TYPE_LABELS.other).toBe('Outro')
    })
  })
})
