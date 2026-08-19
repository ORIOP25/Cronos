import React from 'react'

const AUTO_RECOVERY_KEY = 'cronos:error-boundary:last-reload'
const AUTO_RECOVERY_COOLDOWN_MS = 30_000

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Erro capturado pelo ErrorBoundary:', error, errorInfo)
    this.attemptAutomaticRecovery()
  }

  reloadPage = () => {
    if (this.props.onReset) {
      this.props.onReset()
      return
    }

    globalThis.location.reload()
  }

  attemptAutomaticRecovery = () => {
    try {
      const lastReload = Number(globalThis.sessionStorage.getItem(AUTO_RECOVERY_KEY) ?? 0)
      if (Date.now() - lastReload < AUTO_RECOVERY_COOLDOWN_MS) return

      globalThis.sessionStorage.setItem(AUTO_RECOVERY_KEY, String(Date.now()))
    } catch (storageError) {
      console.error('Não foi possível proteger a recuperação automática:', storageError)
      return
    }

    this.reloadPage()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          onReload: this.reloadPage,
        })
      }

      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            padding: '48px',
            textAlign: 'center',
            fontFamily: 'var(--font-body)',
            color: 'var(--brand-950)',
          }}
        >
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'var(--color-state-gap-bg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '24px',
              fontSize: '1.5rem',
            }}
          >
            !
          </div>
          <h2
            className="text-display"
            style={{ fontSize: '1.5rem', marginBottom: '12px', color: 'var(--brand-950)' }}
          >
            Algo correu mal
          </h2>
          <p style={{ color: 'var(--brand-600)', marginBottom: '24px', maxWidth: '420px', lineHeight: 1.6 }}>
            Ocorreu um erro inesperado ao carregar esta página. Pedimos desculpa pelo incómodo.
          </p>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              type="button"
              className="btn-zen btn-zen-primary"
              onClick={this.reloadPage}
            >
              Tentar novamente
            </button>
            <button
              type="button"
              className="btn-zen btn-zen-outline"
              onClick={() => {
                globalThis.location.href = '/dashboard'
              }}
            >
              Ir para o painel
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
