import { useEffect, useState } from 'react'

const SLOW_REQUEST_MILLISECONDS = 5000

/**
 * Marks a long-running request after five seconds so the UI can explain the wait.
 */
export function useSlowRequest(isLoading) {
  const [isSlowRequest, setIsSlowRequest] = useState(false)

  useEffect(() => {
    if (!isLoading) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsSlowRequest(false)
      return undefined
    }
    const timer = setTimeout(() => setIsSlowRequest(true), SLOW_REQUEST_MILLISECONDS)
    return () => clearTimeout(timer)
  }, [isLoading])

  return isSlowRequest
}

export { SLOW_REQUEST_MILLISECONDS }
