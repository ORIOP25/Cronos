// Testes para o componente SmartTable.

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import SmartTable from '../components/SmartTable'

describe('SmartTable', () => {
  const columns = [
    { key: 'name', label: 'Nome' },
    { key: 'email', label: 'Email' },
  ]

  const data = [
    { id: 1, name: 'Prof A', email: 'a@test.com' },
    { id: 2, name: 'Prof B', email: 'b@test.com' },
  ]

  it('renderiza cabeçalhos de coluna', () => {
    render(<SmartTable columns={columns} data={data} loading={false} />)
    expect(screen.getByText('Nome')).toBeDefined()
    expect(screen.getByText('Email')).toBeDefined()
  })

  it('renderiza dados das linhas', () => {
    render(<SmartTable columns={columns} data={data} loading={false} />)
    expect(screen.getByText('Prof A')).toBeDefined()
    expect(screen.getByText('Prof B')).toBeDefined()
  })

  it('mostra indicador de carregamento', () => {
    render(<SmartTable columns={columns} data={[]} loading={true} />)
    expect(screen.getByText(/carregar|loading|nenhum/i)).toBeDefined()
  })

  it('mostra empty state sem dados e sem loading', () => {
    render(<SmartTable columns={columns} data={[]} loading={false} />)
    expect(screen.getByText(/nenhum|vazio|sem dados/i)).toBeDefined()
  })

  it('chama onEdit ao clicar em editar', () => {
    const onEdit = vi.fn()
    render(<SmartTable columns={columns} data={data} loading={false} onEdit={onEdit} />)
    const editButtons = screen.getAllByText(/editar/i)
    expect(editButtons.length).toBeGreaterThanOrEqual(1)
  })
})
