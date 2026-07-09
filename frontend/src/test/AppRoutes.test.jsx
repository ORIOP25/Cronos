import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import App from '../App'

function renderAppAt(path) {
  window.history.replaceState({}, '', path)
  return renderWithProviders(<App />)
}

describe('App route polish', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ isSignedIn: false, isLoaded: true })
  })

  it('redirects /sign-in to /login', async () => {
    renderAppAt('/sign-in')

    await waitFor(() => {
      expect(window.location.pathname).toBe('/login')
    })
  })

  it('redirects /sign-up to /register', async () => {
    renderAppAt('/sign-up')

    await waitFor(() => {
      expect(window.location.pathname).toBe('/register')
    })
  })

  it('renders a friendly 404 for unknown routes', async () => {
    renderAppAt('/rota-inexistente')

    expect(await screen.findByRole('heading', { name: /página não encontrada/i })).toBeInTheDocument()
    expect(screen.getByText(/rota-inexistente/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /voltar ao início/i })).toHaveAttribute('href', '/')
  })
})
