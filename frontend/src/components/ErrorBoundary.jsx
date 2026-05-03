import React from 'react'
import PropTypes from 'prop-types'

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
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null })
    if (this.props.onReset) {
      this.props.onReset()
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          onReload: this.handleReload,
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
              onClick={this.handleReload}
            >
              Tentar novamente
            </button>
            <button
              type="button"
              className="btn-zen btn-zen-outline"
              onClick={() => {
                window.location.href = '/dashboard'
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

ErrorBoundary.propTypes = {
  children: PropTypes.node.isRequired,
  fallback: PropTypes.func,
  onReset: PropTypes.func,
}

export default ErrorBoundary
