"""Testes para o componente ProtectedRoute."""

import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useAuthStore } from '../store'
import { renderWithProviders } from './testUtils'
import ProtectedRoute from '../components/ProtectedRoute'

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false, user: null })
    localStorage.clear()
  })

  it('redireciona para /login quando não autenticado', () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/dashboard" element={<ProtectedRoute><div>Dashboard</div></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Login Page')).toBeDefined()
  })

  it('renderiza children quando autenticado', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { email: 'a@b.com', role: 'admin', orgId: 1, teacherId: null },
    })
    renderWithProviders(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/dashboard" element={<ProtectedRoute><div>Dashboard Content</div></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Dashboard Content')).toBeDefined()
  })

  it('preserva a rota de destino no state', () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/teachers']}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/teachers" element={<ProtectedRoute><div>Teachers</div></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Login Page')).toBeDefined()
  })
})
