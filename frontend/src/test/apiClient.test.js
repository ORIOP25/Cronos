import { describe, it, expect } from 'vitest'
import apiClient, { setClerkTokenGetter } from '../apiClient'

describe('apiClient', () => {
  it('has withCredentials enabled (T24)', () => {
    expect(apiClient.defaults.withCredentials).toBe(true)
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
