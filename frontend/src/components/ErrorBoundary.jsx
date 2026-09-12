import React from 'react'
import FailureState from './FailureState'
import { getApiErrorPresentation } from '../utils/apiErrors'

const AUTO_RECOVERY_KEY = 'cronos:error-boundary:last-reload'
const AUTO_RECOVERY_COOLDOWN_MS = 30_000

const isChunkLoadFailure = (error) => /chunk|dynamically imported module|importing a module script failed/i.test(error?.message || '')

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
    if (isChunkLoadFailure(error)) this.attemptAutomaticRecovery()
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
          presentation={getApiErrorPresentation(this.state.error)}
          onRetry={this.reloadPage}
          navigationTo="/dashboard"
        />
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
