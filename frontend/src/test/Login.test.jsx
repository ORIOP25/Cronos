// Testes para a página de Login.

import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'
import Login from '../pages/Login'

vi.mock('../apiClient', () => ({
  default: {
    post: vi.fn(),
    interceptors: { response: { use: vi.fn() } },
  },
  auth: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}))

describe('Login page', () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false, user: null })
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('renderiza formulário de login com campos email e password', () => {
    renderWithProviders(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    expect(screen.getByPlaceholderText(/email/i)).toBeDefined()
    expect(screen.getByPlaceholderText(/password/i)).toBeDefined()
  })

  it('tem link para registo', () => {
    renderWithProviders(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    const link = screen.getByText(/regist/i)
    expect(link).toBeDefined()
  })

  it('redireciona para dashboard se já autenticado', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { email: 'admin@test.com', role: 'admin', orgId: 1, teacherId: null },
    })
    renderWithProviders(
      <MemoryRouter initialEntries={['/login']}>
        <Login />
      </MemoryRouter>
    )
    expect(screen.queryByPlaceholderText(/email/i)).toBeNull()
  })
})
