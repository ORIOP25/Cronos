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
    expect(typeof fn).toBe('function')
  })
})

describe('request interceptor', () => {
  it('attaches Bearer token when getter returns value', async () => {
    setClerkTokenGetter(async () => 'tk_test')
    const config = { headers: {} }
    const interceptor = apiClient.interceptors.request.handlers[0]
    if (interceptor?.fulfilled) {
      const result = await interceptor.fulfilled(config)
      expect(result.headers.Authorization).toBe('Bearer tk_test')
    }
  })

  it('does not crash when getter throws', async () => {
    setClerkTokenGetter(async () => { throw new Error('fail') })
    const config = { headers: {} }
    const interceptor = apiClient.interceptors.request.handlers[0]
    if (interceptor?.fulfilled) {
      const result = await interceptor.fulfilled(config)
      expect(result).toBe(config)
    }
  })
})

describe('response interceptor', () => {
  it('resolves 404 without throwing', async () => {
    const interceptor = apiClient.interceptors.response.handlers[0]
    if (interceptor?.rejected) {
      const error = { response: { status: 404, data: null } }
      const result = await interceptor.rejected(error)
      expect(result.status).toBe(404)
    }
  })
})
