import { useEffect, useRef, useState } from 'react'

const LOAD_TIMEOUT_MS = 3000
let turnstileScriptPromise

function loadTurnstileScript() {
  if (window.turnstile?.render) return Promise.resolve(window.turnstile)
  if (turnstileScriptPromise) return turnstileScriptPromise.then(() => window.turnstile)

  turnstileScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-cronos-turnstile]')
    if (existing) {
      existing.addEventListener('load', () => resolve(window.turnstile), { once: true })
      existing.addEventListener('error', () => reject(new Error('Turnstile script failed to load.')), { once: true })
      return
    }
    const script = document.createElement('script')
    script.async = true
    script.defer = true
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.dataset.cronosTurnstile = 'true'
    script.onload = () => resolve(window.turnstile)
    script.onerror = () => {
      script.remove()
      turnstileScriptPromise = undefined
      reject(new Error('Turnstile script failed to load.'))
    }
    document.head.appendChild(script)
  })
  return turnstileScriptPromise
}

export default function TurnstileWidget({ onSuccess, onExpired, onError, resetVersion }) {
  const elementReference = useRef(null)
  const widgetReference = useRef(null)
  const [loadError, setLoadError] = useState(() => import.meta.env.VITE_TURNSTILE_SITE_KEY ? '' : 'Não foi possível carregar a verificação anti-spam.')

  useEffect(() => {
    let timeoutId
    let disposed = false
    const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY
    const renderWidget = (turnstile) => {
      if (disposed || widgetReference.current !== null || !elementReference.current || !siteKey || !turnstile?.render) return
      widgetReference.current = turnstile.render(elementReference.current, { sitekey: siteKey, action: 'contact', callback: onSuccess, 'expired-callback': onExpired, 'error-callback': onError })
      setLoadError('')
    }

    if (siteKey) {
      timeoutId = window.setTimeout(() => { if (!disposed && widgetReference.current === null) setLoadError('Não foi possível carregar a verificação anti-spam.') }, LOAD_TIMEOUT_MS)
      loadTurnstileScript().then(renderWidget).catch(() => { if (!disposed) setLoadError('Não foi possível carregar a verificação anti-spam.') })
    }
    return () => { disposed = true; if (timeoutId) window.clearTimeout(timeoutId); if (widgetReference.current !== null) window.turnstile?.remove?.(widgetReference.current); widgetReference.current = null }
  }, [onError, onExpired, onSuccess])

  useEffect(() => { if (resetVersion > 0 && widgetReference.current !== null) window.turnstile?.reset?.(widgetReference.current) }, [resetVersion])

  return <div className="cronos-turnstile"><div ref={elementReference} />{loadError && <p className="cronos-questionnaire__error" role="alert">{loadError} Pode enviar o pedido por email.</p>}</div>
}
