import { beforeEach, describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ErrorBoundary from '../components/ErrorBoundary'

function BrokenComponent() {
  throw new Error('Erro de teste deliberado')
}

function WorkingComponent() {
  return <div>Funciona</div>
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

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
    const reloadPage = vi.fn()
    render(
      <ErrorBoundary onReset={reloadPage}>
        <BrokenComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Algo correu mal')).toBeInTheDocument()
    expect(screen.getByText('Tentar novamente')).toBeInTheDocument()
    expect(reloadPage).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('permite recuperar quando o utilizador tenta novamente', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const reloadPage = vi.fn()
    render(
      <ErrorBoundary onReset={reloadPage}>
        <BrokenComponent />
      </ErrorBoundary>
    )
    reloadPage.mockClear()

    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    expect(reloadPage).toHaveBeenCalledOnce()
    spy.mockRestore()
  })

  it('recupera automaticamente apenas falhas de módulos após uma atualização', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    function BrokenChunk() {
      throw new Error('Failed to fetch dynamically imported module')
    }

    const firstReload = vi.fn()
    const firstRender = render(
      <ErrorBoundary onReset={firstReload}>
        <BrokenChunk />
      </ErrorBoundary>
    )
    expect(firstReload).toHaveBeenCalledOnce()
    firstRender.unmount()

    const secondReload = vi.fn()
    render(
      <ErrorBoundary onReset={secondReload}>
        <BrokenChunk />
      </ErrorBoundary>
    )

    expect(secondReload).not.toHaveBeenCalled()
    expect(screen.getByText('Algo correu mal')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('tem botão para navegar para o painel', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary onReset={() => {}}>
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
      <ErrorBoundary fallback={fallback} onReset={() => {}}>
        <BrokenComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText(/Custom error/)).toBeInTheDocument()
    spy.mockRestore()
  })
})
