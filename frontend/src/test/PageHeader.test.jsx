import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PageHeader from '../components/PageHeader'

describe('PageHeader', () => {
  it('shows the page title as the only heading', () => {
    render(<PageHeader title="Equipa" />)
    expect(screen.getAllByRole('heading')).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1, name: 'Equipa' })).toBeInTheDocument()
  })

  it('renders actions in their own toolbar below the title', () => {
    render(<PageHeader title="Salas"><button type="button">Nova Sala</button></PageHeader>)
    expect(screen.getByRole('group', { name: 'Ações da página' })).toContainElement(screen.getByRole('button', { name: 'Nova Sala' }))
  })

  it('keeps context and description under the title', () => {
    render(<PageHeader title="Olá, Rui" context="Escola Teste" description="Hoje, segunda." />)
    expect(screen.getByText('Escola Teste')).toBeInTheDocument()
    expect(screen.getByText('Hoje, segunda.')).toBeInTheDocument()
  })
})
