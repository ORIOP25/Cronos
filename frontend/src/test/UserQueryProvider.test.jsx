import { QueryClient, useQuery } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UserQueryProvider } from '../UserQueryProvider'
import { createQueryClient } from '../queryClient'
import { resetClerkState, setClerkState } from './setup'

describe('createQueryClient', () => {
  const errorWithStatus = (status) => ({ response: { status } })

  it.each([400, 401, 403, 404, 422])('does not retry deterministic HTTP %s', (status) => {
    const retry = createQueryClient().getDefaultOptions().queries.retry

    expect(retry(0, errorWithStatus(status))).toBe(false)
  })

  it.each([
    ['network errors', new Error('offline')],
    ['HTTP 408', errorWithStatus(408)],
    ['HTTP 429', errorWithStatus(429)],
    ['HTTP 500', errorWithStatus(500)],
  ])('retries %s at most twice', (_label, error) => {
    const retry = createQueryClient().getDefaultOptions().queries.retry

    expect(retry(0, error)).toBe(true)
    expect(retry(1, error)).toBe(true)
    expect(retry(2, error)).toBe(false)
  })

  it('keeps mutation retries disabled', () => {
    expect(createQueryClient().getDefaultOptions().mutations.retry).toBe(false)
  })
})

describe('UserQueryProvider', () => {
  beforeEach(() => resetClerkState())
  afterEach(() => vi.restoreAllMocks())

  it('replaces and clears cached member data when Clerk identity changes', async () => {
    const clearSpy = vi.spyOn(QueryClient.prototype, 'clear')
    let resolveUserB
    const loadMember = vi.fn()
      .mockResolvedValueOnce({ name: 'User A' })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveUserB = resolve }))

    function CurrentMember() {
      const { data } = useQuery({
        queryKey: ['current-member', 'org_same'],
        queryFn: loadMember,
      })
      return <div>{data?.name ?? 'Loading member'}</div>
    }

    const ui = () => (
      <UserQueryProvider>
        <CurrentMember />
      </UserQueryProvider>
    )
    const { rerender } = render(ui())

    expect(await screen.findByText('User A')).toBeInTheDocument()

    setClerkState({ userId: 'user_b' })
    rerender(ui())

    expect(screen.queryByText('User A')).not.toBeInTheDocument()
    expect(screen.getByText('Loading member')).toBeInTheDocument()
    await waitFor(() => expect(clearSpy).toHaveBeenCalled())

    await act(async () => resolveUserB({ name: 'User B' }))
    expect(await screen.findByText('User B')).toBeInTheDocument()
    expect(loadMember).toHaveBeenCalledTimes(2)
  })

  it('keeps the same user query tree and cache while a session task becomes active', async () => {
    let mounts = 0
    const loadMember = vi.fn().mockResolvedValue({ name: 'User A' })

    function CurrentMember() {
      useEffect(() => {
        mounts += 1
      }, [])
      const { data } = useQuery({
        queryKey: ['current-member', 'org_same'],
        queryFn: loadMember,
      })
      return <div>{data?.name ?? 'Loading member'}</div>
    }

    const ui = () => (
      <UserQueryProvider>
        <CurrentMember />
      </UserQueryProvider>
    )
    const { rerender } = render(ui())

    expect(await screen.findByText('User A')).toBeInTheDocument()
    expect(mounts).toBe(1)

    setClerkState({ sessionStatus: 'pending' })
    rerender(ui())
    expect(screen.getByText('User A')).toBeInTheDocument()
    expect(mounts).toBe(1)

    setClerkState({ sessionStatus: 'active' })
    rerender(ui())
    expect(screen.getByText('User A')).toBeInTheDocument()
    expect(mounts).toBe(1)
    expect(loadMember).toHaveBeenCalledOnce()
  })

  it('replaces the authenticated query client when signing out', async () => {
    const clearSpy = vi.spyOn(QueryClient.prototype, 'clear')
    const loadMember = vi.fn().mockResolvedValue({ name: 'User A' })

    function CurrentMember() {
      const { data } = useQuery({
        queryKey: ['current-member', 'org_same'],
        queryFn: loadMember,
      })
      return <div>{data?.name ?? 'Loading member'}</div>
    }

    const ui = () => <UserQueryProvider><CurrentMember /></UserQueryProvider>
    const { rerender } = render(ui())
    expect(await screen.findByText('User A')).toBeInTheDocument()

    setClerkState({ isSignedIn: false })
    rerender(ui())

    expect(screen.queryByText('User A')).not.toBeInTheDocument()
    await waitFor(() => expect(clearSpy).toHaveBeenCalled())
  })
})
