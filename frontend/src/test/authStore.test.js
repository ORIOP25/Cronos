// Testes para o Zustand auth store do frontend.

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../store'

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
    })
    localStorage.clear()
  })

  it('estado inicial: não autenticado', () => {
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('login define user e isAuthenticated', () => {
    useAuthStore.getState().login({
      user_email: 'admin@test.com',
      role: 'admin',
      teacher_id: null,
      organization_id: 1,
      organization_name: 'Escola Teste',
    })
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.user.email).toBe('admin@test.com')
    expect(state.user.role).toBe('admin')
    expect(state.user.orgId).toBe(1)
  })

  it('logout limpa estado', () => {
    useAuthStore.getState().login({
      user_email: 'admin@test.com',
      role: 'admin',
      teacher_id: null,
      organization_id: 1,
      organization_name: 'Escola Teste',
    })
    useAuthStore.getState().logout()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('login com professor inclui teacherId', () => {
    useAuthStore.getState().login({
      user_email: 'prof@test.com',
      role: 'teacher',
      teacher_id: 42,
      organization_id: 1,
      organization_name: 'Escola Teste',
    })
    expect(useAuthStore.getState().user.teacherId).toBe(42)
  })

  it('persiste estado em localStorage', () => {
    useAuthStore.getState().login({
      user_email: 'admin@test.com',
      role: 'admin',
      teacher_id: null,
      organization_id: 1,
      organization_name: 'Escola Teste',
    })
    const stored = JSON.parse(localStorage.getItem('horario-zen-storage'))
    expect(stored.state.isAuthenticated).toBe(true)
  })
})
