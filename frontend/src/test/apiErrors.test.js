import { describe, expect, it } from 'vitest'
import { getApiErrorMessage } from '../utils/apiErrors'

describe('getApiErrorMessage', () => {
  it('uses plain backend detail strings', () => {
    expect(getApiErrorMessage({ response: { data: { detail: 'Nome obrigatório' } } })).toBe('Nome obrigatório')
  })

  it('joins validation detail arrays', () => {
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'name'], msg: 'Nome obrigatório' },
            { loc: ['body', 'email'], msg: 'Email inválido' },
          ],
        },
      },
    }

    expect(getApiErrorMessage(error)).toBe('Nome obrigatório Email inválido')
  })

  it('reads object message fields', () => {
    expect(getApiErrorMessage({ response: { data: { detail: { message: 'Rascunho desatualizado' } } } })).toBe('Rascunho desatualizado')
  })

  it('falls back to the error message and humanizes operational terms', () => {
    expect(getApiErrorMessage({ message: 'solver error' })).toContain('motor de cálculo')
  })

  it('uses the provided fallback when no useful message exists', () => {
    expect(getApiErrorMessage({}, 'Falha controlada')).toBe('Falha controlada')
  })
})
