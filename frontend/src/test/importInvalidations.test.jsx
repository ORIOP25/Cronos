import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetClerkState, setClerkState } from './setup'

vi.mock('../apiClient', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import apiClient from '../apiClient'
import { useCommitBulkImport } from '../features/imports/data'

function createHarness() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

describe('bulk import invalidations', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ orgId: 'org-a', isSignedIn: true, isLoaded: true })
    vi.clearAllMocks()
    apiClient.post.mockResolvedValue({ created_counts: {} })
  })

  it('invalidates the class availability queries after a commit', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useCommitBulkImport(), { wrapper })
    const file = new File(['x'], 'Cronos_DisponibilidadeTurmas_Template.csv', { type: 'text/csv' })

    await act(() => mutation.result.current.mutateAsync({ class_availability: file }))

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(
      expect.arrayContaining([['class-availability', 'org-a']]),
    )
  })

  it('invalidates every teacher availability reader after a commit', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useCommitBulkImport(), { wrapper })
    const file = new File(
      ['x'],
      'Cronos_DisponibilidadeProfessores_Template.csv',
      { type: 'text/csv' },
    )

    await act(() => mutation.result.current.mutateAsync({ teacher_availability: file }))

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(
      expect.arrayContaining([
        ['teacher-availability', 'org-a'],
        ['substitute-recommendations', 'org-a'],
        ['substitute-diagnostics', 'org-a'],
        ['occurrences', 'org-a'],
        ['teacher-progress', 'org-a'],
        ['my-availability', 'org-a'],
        ['heatmap', 'org-a'],
      ]),
    )
  })

  it('invalidates every teacher presence reader after a commit', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useCommitBulkImport(), { wrapper })
    const file = new File(['x'], 'Cronos_PresencaProfessores_Template.csv', { type: 'text/csv' })

    await act(() => mutation.result.current.mutateAsync({ teacher_presence: file }))

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(
      expect.arrayContaining([
        ['teacher-presence', 'org-a'],
        ['my-presence', 'org-a'],
        ['members', 'org-a'],
        ['teacher-availability', 'org-a'],
      ]),
    )
  })
})
