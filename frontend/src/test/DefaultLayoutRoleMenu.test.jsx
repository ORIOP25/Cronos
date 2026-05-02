import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DefaultLayout from '../components/DefaultLayout'
import { useAuthStore } from '../store'
import { renderWithProviders } from './testUtils'

function renderLayout() {
  return renderWithProviders(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<DefaultLayout />}>
          <Route index element={<div>PAGINA_TESTE</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('DefaultLayout role menu', () => {
  beforeEach(() => {
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
    })
  })

  it('admin nao ve tabs de professor no menu', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'admin@test.pt',
        role: 'admin',
        teacherId: null,
        orgId: 1,
      },
    })

    renderLayout()

    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Horários' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Minhas Preferências' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Meus Horários' })).not.toBeInTheDocument()
  })

  it('professor ve exatamente Minhas Preferencias e Meus Horarios', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'prof@test.pt',
        role: 'teacher',
        teacherId: 10,
        orgId: 1,
      },
    })

    renderLayout()

    expect(screen.getByRole('link', { name: 'Preferências' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Meus Horários' })).toBeInTheDocument()

    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Horários' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Professores' })).not.toBeInTheDocument()
  })
})
