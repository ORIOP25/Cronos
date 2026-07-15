import { useCallback, useEffect, useRef, useState } from 'react'

export function useTransientMessage() {
  const [message, setMessage] = useState(null)
  const timer = useRef(null)
  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    setMessage(null)
  }, [])
  const show = useCallback((value, durationMs = 3000) => {
    if (timer.current) clearTimeout(timer.current)
    setMessage(value)
    timer.current = setTimeout(() => {
      timer.current = null
      setMessage(null)
    }, durationMs)
  }, [])
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])
  return { message, show, clear }
}
