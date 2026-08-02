import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTestQueryClient } from './testUtils'
import { QueryClientProvider } from '@tanstack/react-query'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('../apiClient', () => ({ default: { post } }))

import { useSubmitContact } from '../features/contact/data'

describe('useSubmitContact', () => {
  beforeEach(() => post.mockReset())

  it('posts payloads to the contact endpoint', async () => {
    post.mockResolvedValue(undefined)
    const queryClient = createTestQueryClient()
    const wrapper = ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSubmitContact(), { wrapper })
    const payload = { name: 'Ana', website: '' }
    await result.current.mutateAsync(payload)
    expect(post).toHaveBeenCalledWith('/contact', payload)
  })
})
