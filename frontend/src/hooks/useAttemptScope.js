import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useAuth, useOrganization } from '@clerk/react'

/**
 * Guards asynchronous attempts with the identity and lifecycle that started them.
 * Capture the scope before a request and check it before emitting feedback or
 * changing local state that belongs to the current context.
 */
export function useAttemptScope() {
  const { userId } = useAuth()
  const { organization } = useOrganization()
  const scope = `${userId ?? 'signed-out'}:${organization?.id ?? 'none'}`
  const scopeRef = useRef(scope)
  const mountedRef = useRef(true)

  useEffect(() => {
    scopeRef.current = scope
  }, [scope])

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const capture = useCallback(() => scopeRef.current, [])

  const isCurrent = useCallback((captured) => (
    mountedRef.current && captured === scopeRef.current
  ), [])

  const guard = useCallback((options = {}) => {
    const captured = scopeRef.current
    return {
      ...options,
      onSuccess: options.onSuccess
        ? (...args) => { if (isCurrent(captured)) options.onSuccess(...args) }
        : undefined,
      onError: options.onError
        ? (...args) => { if (isCurrent(captured)) options.onError(...args) }
        : undefined,
    }
  }, [isCurrent])

  return useMemo(() => ({ capture, isCurrent, guard }), [capture, guard, isCurrent])
}
