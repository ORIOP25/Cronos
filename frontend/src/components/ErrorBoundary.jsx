import React from 'react'
import FailureState from './FailureState'
import { getApiErrorPresentation } from '../utils/apiErrors'

const AUTO_RECOVERY_KEY = 'cronos:error-boundary:last-reload'
const AUTO_RECOVERY_COOLDOWN_MS = 30_000
const CLIENT_ERROR_CHARACTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

const isChunkLoadFailure = (error) => /chunk|dynamically imported module|importing a module script failed/i.test(error?.message || '')

const newClientErrorReference = () => {
  const values = new Uint8Array(12)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(values)
  else if (globalThis.crypto?.randomUUID) {
    const source = globalThis.crypto.randomUUID().replace(/-/g, '').toUpperCase()
    return `${source}000000000000`.slice(0, 12)
  } else {
    return 'AAAAAAAAAAAA'
  }
  return Array.from(values, (value) => CLIENT_ERROR_CHARACTERS[value % CLIENT_ERROR_CHARACTERS.length]).join('')
}

const clientErrorRevision = () => {
  const revision = import.meta.env.VITE_APP_REVISION || 'local'
  return String(revision).replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64) || 'local'
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, reference: null }
    this.reportedReference = null
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Erro capturado pelo ErrorBoundary:', error, errorInfo)
    const reference = this.state.reference || newClientErrorReference()
    if (!this.state.reference) this.setState({ reference })
    this.reportClientError(reference, isChunkLoadFailure(error) ? 'chunk_load_error' : 'render_error')
    if (isChunkLoadFailure(error)) this.attemptAutomaticRecovery()
  }

  reportClientError = (reference, category) => {
    if (this.reportedReference === reference || typeof globalThis.fetch !== 'function') return
    this.reportedReference = reference
    void globalThis.fetch('/api/v1/client-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reference, category, revision: clientErrorRevision() }),
      keepalive: true,
    }).catch(() => {})
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
      const revision = import.meta.env.VITE_APP_REVISION || 'local'
      const recoveryKey = `${AUTO_RECOVERY_KEY}:${revision}`
      const lastReload = Number(globalThis.sessionStorage.getItem(recoveryKey) ?? 0)
      if (Date.now() - lastReload < AUTO_RECOVERY_COOLDOWN_MS) return

      globalThis.sessionStorage.setItem(recoveryKey, String(Date.now()))
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
        <FailureState
          presentation={{ ...getApiErrorPresentation(this.state.error), reference: this.state.reference }}
          onRetry={this.reloadPage}
          navigationTo="/dashboard"
        />
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
