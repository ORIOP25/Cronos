import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from '../components/ErrorBoundary'

function BrokenComponent() {
  throw new Error('Erro de teste deliberado')
}

function WorkingComponent() {
  return <div>Funciona</div>
}

describe('ErrorBoundary', () => {
  it('renderiza children quando não há erro', () => {
    render(
      <ErrorBoundary>
        <WorkingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Funciona')).toBeInTheDocument()
  })

  it('mostra ecrã de erro quando um filho lança exceção', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <BrokenComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Algo correu mal')).toBeInTheDocument()
    expect(screen.getByText('Tentar novamente')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('tem botão para navegar para o painel', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <BrokenComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Ir para o painel')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('usa fallback customizado quando fornecido', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fallback = vi.fn(({ error, onReload }) => (
      <div>
        <span>Custom error: {error.message}</span>
        <button onClick={onReload}>Recarregar</button>
      </div>
    ))
    render(
      <ErrorBoundary fallback={fallback}>
        <BrokenComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText(/Custom error/)).toBeInTheDocument()
    spy.mockRestore()
  })
})
