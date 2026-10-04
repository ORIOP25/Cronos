import { act } from 'react'
import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { resetClerkState, setClerkState } from './setup'

describe('useAttemptScope', () => {
  afterEach(() => {
    resetClerkState()
  })

  it('keeps an attempt current while the identity is unchanged', () => {
    setClerkState({ userId: 'user_a', orgId: 1 })
    const { result } = renderHook(() => useAttemptScope())

    const attempt = result.current.capture()
    expect(result.current.isCurrent(attempt)).toBe(true)
  })

  it('invalidates an attempt after the organization changes', () => {
    setClerkState({ userId: 'user_a', orgId: 1 })
    const { result, rerender } = renderHook(() => useAttemptScope())
    const attempt = result.current.capture()

    act(() => { setClerkState({ orgId: 2 }) })
    rerender()

    expect(result.current.isCurrent(attempt)).toBe(false)
    expect(result.current.isCurrent(result.current.capture())).toBe(true)
  })

  it('invalidates an attempt after the user signs out', () => {
    setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
    const { result, rerender } = renderHook(() => useAttemptScope())
    const attempt = result.current.capture()

    act(() => { setClerkState({ isSignedIn: false, userId: null, orgId: null }) })
    rerender()

    expect(result.current.isCurrent(attempt)).toBe(false)
  })

  it('invalidates an attempt after the component unmounts', () => {
    setClerkState({ userId: 'user_a', orgId: 1 })
    const { result, unmount } = renderHook(() => useAttemptScope())
    const attempt = result.current.capture()

    unmount()

    expect(result.current.isCurrent(attempt)).toBe(false)
  })

  it('guards mutation callbacks with the scope captured at attempt start', () => {
    setClerkState({ userId: 'user_a', orgId: 1 })
    const { result, rerender } = renderHook(() => useAttemptScope())
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const guarded = result.current.guard({ onSuccess, onError })

    guarded.onSuccess('ok')
    guarded.onError(new Error('failure'))
    expect(onSuccess).toHaveBeenCalledWith('ok')
    expect(onError).toHaveBeenCalledTimes(1)

    act(() => { setClerkState({ orgId: 2 }) })
    rerender()

    guarded.onSuccess('late')
    guarded.onError(new Error('late failure'))
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledTimes(1)
  })
})
