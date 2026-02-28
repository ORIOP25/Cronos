// Ficheiro: frontend/src/test/store.test.js
/**
 * TESTES — Zustand Store (useAuthStore)
 * ======================================
 * Verifica estado de autenticação: login, logout, persistência.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../store'

describe('useAuthStore', () => {
  beforeEach(() => {
    // Reset store state
    useAuthStore.getState().logout()
  })

  it('estado inicial: não autenticado', () => {
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('login define user e isAuthenticated', () => {
    useAuthStore.getState().login({
      user_email: 'admin@escola.pt',
      role: 'admin',
      teacher_id: null,
      organization_id: 1,
    })
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.user.email).toBe('admin@escola.pt')
    expect(state.user.role).toBe('admin')
    expect(state.user.orgId).toBe(1)
  })

  it('logout limpa estado', () => {
    // Login primeiro
    useAuthStore.getState().login({
      user_email: 'prof@escola.pt',
      role: 'teacher',
      teacher_id: 5,
      organization_id: 2,
    })
    expect(useAuthStore.getState().isAuthenticated).toBe(true)

    // Logout
    useAuthStore.getState().logout()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('login com professor inclui teacherId', () => {
    useAuthStore.getState().login({
      user_email: 'prof@escola.pt',
      role: 'teacher',
      teacher_id: 42,
      organization_id: 3,
    })
    const state = useAuthStore.getState()
    expect(state.user.teacherId).toBe(42)
  })
})
