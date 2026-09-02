// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { getApiErrorCode, getApiErrorMessage } from '../utils/apiErrors'

describe('getApiErrorMessage', () => {
  it('reads a structured backend error code', () => {
    expect(getApiErrorCode({
      response: { data: { detail: { code: 'HOLIDAY_SYNC_FAILED', message: 'Falha' } } },
    })).toBe('HOLIDAY_SYNC_FAILED')
    expect(getApiErrorCode({ response: { data: { detail: 'Falha' } } })).toBeNull()
  })

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

  it('uses a clear message when the server is unreachable', () => {
    expect(getApiErrorMessage({ code: 'ERR_NETWORK', message: 'Network Error' }))
      .toBe('Não foi possível ligar ao servidor. Verifique a ligação e tente novamente.')
  })

  it.each([
    [401, 'A sua sessão terminou. Entre novamente.'],
    [403, 'Não tem permissão para realizar esta ação.'],
    [500, 'O servidor encontrou um problema. Tente novamente dentro de instantes.'],
  ])('maps an empty HTTP %s response to actionable copy', (status, expected) => {
    expect(getApiErrorMessage({ response: { status, data: {} } })).toBe(expected)
  })

  it('does not replace a useful backend detail with a generic status message', () => {
    expect(getApiErrorMessage({
      response: { status: 500, data: { detail: 'O motor de cálculo está indisponível.' } },
    })).toBe('O motor de cálculo está indisponível.')
  })

  it('uses the provided fallback when no useful message exists', () => {
    expect(getApiErrorMessage({}, 'Falha controlada')).toBe('Falha controlada')
  })
})
