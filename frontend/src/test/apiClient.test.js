"""Testes para o apiClient (Axios + interceptors de auth)."""

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

let mockPost
let mockGet

beforeEach(() => {
  mockPost = vi.fn()
  mockGet = vi.fn()
  vi.doMock('axios', () => ({
    default: {
      create: () => ({
        interceptors: { response: { use: (_, fn) => { /* store interceptor */ } } },
        post: mockPost,
        get: mockGet,
        defaults: { headers: { common: {} } },
      }),
      isAxiosError: (e) => e?.isAxiosError === true,
    },
  }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('apiClient', () => {
  it('auth.login envia credenciais como form-urlencoded', async () => {
    const { auth } = await import('../apiClient')
    mockPost.mockResolvedValueOnce({ data: { access_token: 'tok', token_type: 'bearer' } })

    await auth.login({ email: 'a@b.com', password: 'pass' })

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body, config] = mockPost.mock.calls[0]
    expect(url).toBe('/auth/token')
    expect(config.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
  })

  it('auth.register chama endpoint correto', async () => {
    const { auth } = await import('../apiClient')
    mockPost.mockResolvedValueOnce({ data: {} })

    await auth.register({ school_name: 'Escola', admin_name: 'Admin', email: 'a@b.com', password: '123456' })

    expect(mockPost).toHaveBeenCalledWith('/auth/register', expect.any(Object))
  })

  it('auth.logout chama endpoint correto', async () => {
    const { auth } = await import('../apiClient')
    mockPost.mockResolvedValueOnce({ data: { message: 'logout_ok' } })

    await auth.logout()

    expect(mockPost).toHaveBeenCalledWith('/auth/logout')
  })

  it('teachers.getAll chama endpoint correto', async () => {
    const { teachers } = await import('../apiClient')
    mockGet.mockResolvedValueOnce({ data: [] })

    await teachers.getAll()

    expect(mockGet).toHaveBeenCalledWith('/teachers/')
  })
})
