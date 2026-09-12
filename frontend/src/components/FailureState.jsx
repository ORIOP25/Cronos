import { useState } from 'react'

export default function FailureState({
  presentation,
  onRetry,
  navigationTo,
  navigationLabel = 'Ir para o painel',
  retryLabel = 'Tentar novamente',
  secondaryAction = null,
  variant = 'full-page',
}) {
  const [copied, setCopied] = useState(false)
  const reference = presentation?.reference
  const copyReference = async () => {
    if (!reference || !globalThis.navigator?.clipboard) return
    try {
      await globalThis.navigator.clipboard.writeText(reference)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className={`failure-state failure-state--${variant}`} role="alert" aria-live="polite">
      <div className="failure-state__icon" aria-hidden="true">!</div>
      <h1>{presentation?.title || 'Algo correu mal'}</h1>
      <p>{presentation?.message || 'Ocorreu um erro inesperado. Tente novamente.'}</p>
      <div className="failure-state__actions">
        {onRetry && (
          <button type="button" className="btn-zen btn-zen-primary" onClick={onRetry}>
            {retryLabel}
          </button>
        )}
        {navigationTo && (
          <a href={navigationTo} className="btn-zen btn-zen-outline">{navigationLabel}</a>
        )}
        {secondaryAction}
      </div>
      {reference && (
        <div className="failure-state__reference">
          <span>Referência para apoio: <code>{reference}</code></span>
          <button type="button" className="btn-zen-ghost" onClick={() => void copyReference()}>
            {copied ? 'Copiada' : 'Copiar referência'}
          </button>
        </div>
      )}
    </section>
  )
}
