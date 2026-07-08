import { describe, it, expect } from 'vitest'
import apiClient, { setClerkTokenGetter } from '../apiClient'

describe('apiClient', () => {
  it('has withCredentials enabled (T24)', () => {
    expect(apiClient.defaults.withCredentials).toBe(true)
  })

  it('has response interceptor handlers', () => {
    expect(apiClient.interceptors.response.handlers.length).toBeGreaterThanOrEqual(1)
  })
})

describe('setClerkTokenGetter', () => {
  it('accepts and stores a function', () => {
    const fn = async () => 'test_token'
    setClerkTokenGetter(fn)
    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled
    expect(interceptor).toBeTypeOf('function')
  })
})

describe('request interceptor', () => {
  it('attaches Bearer token when getter returns value', async () => {
    setClerkTokenGetter(async () => 'tk_test')
    const config = { headers: {} }
    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled
    expect(interceptor).toBeTypeOf('function')

    const result = await interceptor(config)
    expect(result.headers.Authorization).toBe('Bearer tk_test')
  })

  it('continues without auth header when token getter throws', async () => {
    setClerkTokenGetter(async () => { throw new Error('fail') })
    const config = { headers: {} }
    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled
    expect(interceptor).toBeTypeOf('function')

    const result = await interceptor(config)
    expect(result).toBe(config)
    expect(result.headers.Authorization).toBeUndefined()
  })
})

describe('response interceptor', () => {
  it('rejects 404 errors instead of turning them into empty success', async () => {
    const interceptor = apiClient.interceptors.response.handlers[0]?.rejected
    expect(interceptor).toBeTypeOf('function')

    const error = { response: { status: 404, data: null } }
    await expect(interceptor(error)).rejects.toBe(error)
  })

  it('rejects non-404 errors', async () => {
    const interceptor = apiClient.interceptors.response.handlers[0]?.rejected
    const error = { response: { status: 500, data: { detail: 'fail' } } }

    await expect(interceptor(error)).rejects.toBe(error)
  })

  it('does not mutate global state for 403 errors', async () => {
    const interceptor = apiClient.interceptors.response.handlers[0]?.rejected
    delete globalThis._403_toast_shown
    const error = { response: { status: 403, data: { detail: 'Sem permissões' } } }

    await expect(interceptor(error)).rejects.toBe(error)
    expect(globalThis._403_toast_shown).toBeUndefined()
  })
})
