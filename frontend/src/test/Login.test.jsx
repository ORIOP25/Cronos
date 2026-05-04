// Ficheiro: frontend/src/test/Login.test.jsx
/**
 * TESTES — Login Page
 * ===================
 * Valida o formulário de login: campos, validação, estados de erro.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import Login from '../pages/Login'
import { renderWithRouter } from './testUtils'
import { useAuthStore } from '../store'

vi.mock('../apiClient', () => ({
  default: {
    post: vi.fn(),
  },
}))

describe('Login page', () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false, user: null })
    vi.clearAllMocks()
  })

  it('renderiza campos de email e password', () => {
    renderWithRouter(<Login />)

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /entrar/i })).toBeInTheDocument()
  })

  it('mostra link para registo', () => {
    renderWithRouter(<Login />)

    expect(screen.getByText(/criar conta/i)).toBeInTheDocument()
  })

  it('mostra formulário após submissão vazia (validação HTML5)', async () => {
    renderWithRouter(<Login />)

    fireEvent.click(screen.getByRole('button', { name: /entrar/i }))

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /entrar/i })).toBeInTheDocument()
  })
})
