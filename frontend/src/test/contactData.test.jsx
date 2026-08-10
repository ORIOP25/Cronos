import { QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getContactEndpoint, useSubmitContact } from '../features/contact/data'
import { createTestQueryClient } from './testUtils'

describe('public contact data', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('builds the contact URL from the API base without a duplicate slash', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.cronos.pt/api/v1/')
    expect(getContactEndpoint()).toBe('https://api.cronos.pt/api/v1/contact')
  })

  it('sends JSON with native fetch and accepts 204', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    fetch.mockResolvedValue(new Response(null, { status: 204 }))
    const wrapper = ({ children }) => <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSubmitContact(), { wrapper })
    await result.current.mutateAsync({ name: 'Ana', website: '', turnstile_token: 'token' })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/v1/contact', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Ana', website: '', turnstile_token: 'token' }),
    }))
  })

  it('does not retry a failed submission', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ detail: 'Pedido inválido.' }), { status: 400, headers: { 'Content-Type': 'application/json' } }))
    const wrapper = ({ children }) => <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSubmitContact(), { wrapper })
    await expect(result.current.mutateAsync({})).rejects.toMatchObject({ response: { status: 400 } })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
