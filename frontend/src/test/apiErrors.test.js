import { describe, expect, it } from 'vitest'
import { getApiErrorCode, getApiErrorMessage, getApiErrorPresentation } from '../utils/apiErrors'

describe('api error contract', () => {
  it('uses the safe public message for a known code', () => {
    const error = {
      response: {
        data: {
          detail: {
            code: 'TIMED_OUT',
            message: 'technical solver details must not be shown',
            reference: 'ABC123DEF456',
          },
        },
      },
    }

    expect(getApiErrorCode(error)).toBe('TIMED_OUT')
    expect(getApiErrorMessage(error, 'fallback')).toContain('cinco minutos')
    expect(getApiErrorMessage(error)).not.toContain('technical solver')
    expect(getApiErrorPresentation(error).reference).toBe('ABC123DEF456')
  })

  it('uses the request header when the body has no reference', () => {
    const error = {
      response: {
        status: 503,
        headers: { 'x-request-id': 'REQ123ABC789' },
        data: { detail: { code: 'service_unavailable' } },
      },
    }

    const presentation = getApiErrorPresentation(error)
    expect(presentation.message).toContain('instantes')
    expect(presentation.reference).toBe('REQ123ABC789')
    expect(presentation.retryable).toBe(true)
  })

  it('presents invalid internship flow input as a validation error', () => {
    const presentation = getApiErrorPresentation({
      response: { status: 400, data: { detail: { code: 'INTERNSHIP_FLOW_INVALID' } } },
    })

    expect(presentation.code).toBe('INTERNSHIP_FLOW_INVALID')
    expect(presentation.title).toContain('fluxo')
    expect(presentation.message).toContain('turmas')
    expect(presentation.supportRequired).toBe(false)
  })

  it('maps status and context when the server cannot provide a code', () => {
    expect(getApiErrorPresentation({ response: { status: 401 } }, 'auth').code)
      .toBe('authentication_required')
    expect(getApiErrorPresentation({ response: { status: 403 } }, 'team.sync').code)
      .toBe('access_forbidden')
    expect(getApiErrorPresentation({}, 'team.invite').code)
      .toBe('invitation_delivery_failed')
  })

  it('does not expose arbitrary client or server error text', () => {
    const error = { message: 'database password and stack trace' }
    const message = getApiErrorMessage(error, 'Mensagem local')
    expect(message).toBe('Mensagem local')
    expect(message).not.toContain('password')

    const unknown = getApiErrorPresentation({
      response: { data: { detail: { code: 'internal_debug_code', message: 'secret' } } },
    })
    expect(unknown.message).toBe('Ocorreu um erro inesperado. Tente novamente.')
    expect(unknown.message).not.toContain('secret')
  })

  it('identifies network failures without leaking the original message', () => {
    const presentation = getApiErrorPresentation({ code: 'ERR_NETWORK', message: 'ECONNREFUSED 127.0.0.1' })
    expect(presentation.title).toBe('Ligação indisponível')
    expect(presentation.message).toContain('Verifique a ligação')
    expect(presentation.message).not.toContain('ECONNREFUSED')
  })
})
