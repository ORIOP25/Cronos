// @vitest-environment node
import axios from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import apiClient, { setClerkTokenGetter } from '../apiClient'

function response(config, data, status = 200) {
  return {
    config,
    data,
    headers: {},
    status,
    statusText: status === 204 ? 'No Content' : 'OK',
  }
}

describe('apiClient public contract', () => {
  beforeEach(() => setClerkTokenGetter(async () => null))

  it('does not send browser credentials and resolves successful response payloads directly', async () => {
    const adapter = vi.fn(async (config) => response(config, { value: 42 }))

    await expect(apiClient.get('/contract', { adapter })).resolves.toEqual({ value: 42 })
    expect(adapter.mock.calls[0][0].withCredentials).toBe(false)
  })

  it('resolves a 204 response as undefined', async () => {
    const adapter = vi.fn(async (config) => response(config, undefined, 204))

    await expect(apiClient.delete('/contract', { adapter })).resolves.toBeUndefined()
  })

  it('preserves Axios errors', async () => {
    const failure = new axios.AxiosError('Forbidden', 'ERR_BAD_RESPONSE', {}, {}, {
      config: {},
      data: { detail: 'denied' },
      headers: {},
      status: 403,
      statusText: 'Forbidden',
    })
    const adapter = vi.fn(async () => { throw failure })

    await expect(apiClient.get('/contract', { adapter })).rejects.toBe(failure)
    expect(failure.response.status).toBe(403)
  })

  it('injects the Clerk bearer token into the final request configuration', async () => {
    setClerkTokenGetter(async () => 'tk_test')
    const adapter = vi.fn(async (config) => response(config, null))

    await apiClient.get('/contract', { adapter })

    expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBe('Bearer tk_test')
  })

  it('preserves an explicitly supplied organization-scoped token', async () => {
    const getter = vi.fn(async () => 'tk_stale')
    setClerkTokenGetter(getter)
    const adapter = vi.fn(async (config) => response(config, null))

    await apiClient.get('/contract', {
      adapter,
      headers: { Authorization: 'Bearer tk_fresh_org' },
    })

    expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBe('Bearer tk_fresh_org')
    expect(getter).not.toHaveBeenCalled()
  })

  it('preserves lowercase explicit authorization header without calling getter', async () => {
    const getter = vi.fn(async () => 'tk_stale')
    setClerkTokenGetter(getter)
    const adapter = vi.fn(async (config) => response(config, null))

    await apiClient.get('/contract', {
      adapter,
      headers: { authorization: 'Bearer tk_lowercase' },
    })

    expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBe('Bearer tk_lowercase')
    expect(getter).not.toHaveBeenCalled()
  })

  it('succeeds with explicit token even if global token getter throws', async () => {
    setClerkTokenGetter(async () => { throw new Error('getter blew up') })
    const adapter = vi.fn(async (config) => response(config, { success: true }))

    const res = await apiClient.get('/contract', {
      adapter,
      headers: { Authorization: 'Bearer tk_explicit' },
    })

    expect(res).toEqual({ success: true })
  })

  it('rejects before sending a request when token retrieval fails', async () => {
    setClerkTokenGetter(async () => { throw new Error('token unavailable') })
    const adapter = vi.fn(async (config) => response(config, null))

    await expect(apiClient.get('/contract', { adapter })).rejects.toThrow('token unavailable')

    expect(adapter).not.toHaveBeenCalled()
  })
})
