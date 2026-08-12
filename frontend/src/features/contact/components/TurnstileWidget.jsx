import { useEffect, useRef, useState } from 'react'

const POLL_INTERVAL_MS = 50
const LOAD_TIMEOUT_MS = 3000

export default function TurnstileWidget({ onSuccess, onExpired, onError, resetVersion }) {
  const elementReference = useRef(null)
  const widgetReference = useRef(null)
  const [loadError, setLoadError] = useState(() => import.meta.env.VITE_TURNSTILE_SITE_KEY ? '' : 'Não foi possível carregar a verificação anti-spam.')

  useEffect(() => {
    let pollId
    let timeoutId
    let disposed = false
    const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY
    const clearTimers = () => { if (pollId) window.clearInterval(pollId); if (timeoutId) window.clearTimeout(timeoutId) }
    const renderWidget = () => {
      if (disposed || widgetReference.current !== null || !elementReference.current || !siteKey || !window.turnstile?.render) return false
      widgetReference.current = window.turnstile.render(elementReference.current, { sitekey: siteKey, action: 'contact', callback: onSuccess, 'expired-callback': onExpired, 'error-callback': onError })
      setLoadError('')
      clearTimers()
      return true
    }

    if (siteKey && !renderWidget()) {
      pollId = window.setInterval(renderWidget, POLL_INTERVAL_MS)
      timeoutId = window.setTimeout(() => { clearTimers(); if (!disposed && widgetReference.current === null) setLoadError('Não foi possível carregar a verificação anti-spam.') }, LOAD_TIMEOUT_MS)
    }
    return () => { disposed = true; clearTimers(); if (widgetReference.current !== null) window.turnstile?.remove?.(widgetReference.current); widgetReference.current = null }
  }, [onError, onExpired, onSuccess])

  useEffect(() => { if (resetVersion > 0 && widgetReference.current !== null) window.turnstile?.reset?.(widgetReference.current) }, [resetVersion])

  return <div className="cronos-turnstile"><div ref={elementReference} />{loadError && <p className="cronos-questionnaire__error" role="alert">{loadError} Pode enviar o pedido por email.</p>}</div>
}
