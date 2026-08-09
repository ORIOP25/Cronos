import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createTestQueryClient } from './testUtils'
import { QueryClientProvider } from '@tanstack/react-query'
import { useSubmitContact } from '../features/contact/data'

describe('useSubmitContact', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => vi.unstubAllGlobals())

  it('sends JSON with native fetch and accepts 204', async () => {
    fetch.mockResolvedValue(new Response(null, { status: 204 }))
    const wrapper = ({ children }) => <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSubmitContact(), { wrapper })
    await result.current.mutateAsync({ name: 'Ana', website: '' })
    expect(fetch).toHaveBeenCalledWith('/api/v1/contact', expect.objectContaining({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Ana', website: '' }) }))
  })

  it('keeps status and detail in the Axios-compatible error shape', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ detail: 'Pedido inválido.' }), { status: 400, headers: { 'Content-Type': 'application/json' } }))
    const wrapper = ({ children }) => <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSubmitContact(), { wrapper })
    await expect(result.current.mutateAsync({})).rejects.toMatchObject({ response: { status: 400, data: { detail: 'Pedido inválido.' } } })
  })
})
