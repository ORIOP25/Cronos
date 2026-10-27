import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import ConfirmationModal from '../components/ConfirmationModal'

describe('ConfirmationModal', () => {
  const defaultProps = {
    visible: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
  }

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    act(() => {
      vi.runOnlyPendingTimers()
    })
    cleanup()
    vi.useRealTimers()
  })

  it('mostra título e mensagem padrão', () => {
    render(<ConfirmationModal {...defaultProps} />)
    expect(screen.getByText('Confirmar Remoção')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Confirmar Remoção' })).toBeInTheDocument()
    expect(screen.getByText(/Tem a certeza/)).toBeInTheDocument()
  })

  it('mostra título e mensagem personalizados', () => {
    render(
      <ConfirmationModal
        {...defaultProps}
        title="Título customizado"
        message="Mensagem customizada"
      />
    )
    expect(screen.getByText('Título customizado')).toBeInTheDocument()
    expect(screen.getByText('Mensagem customizada')).toBeInTheDocument()
  })

  it('chama onClose ao clicar em Cancelar', () => {
    render(<ConfirmationModal {...defaultProps} />)
    fireEvent.click(screen.getByText('Cancelar'))
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('chama onConfirm ao clicar em Confirmar', () => {
    render(<ConfirmationModal {...defaultProps} />)
    fireEvent.click(screen.getByText('Confirmar'))
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1)
  })

  it('mostra texto de confirmação personalizado', () => {
    render(<ConfirmationModal {...defaultProps} confirmText="Sim, remover" />)
    expect(screen.getByText('Sim, remover')).toBeInTheDocument()
  })

  it('desabilita botões durante loading', () => {
    render(<ConfirmationModal {...defaultProps} isLoading={true} />)
    expect(screen.getByText('A guardar…')).toBeInTheDocument()
  })

  it('anuncia que o pedido continua em processamento após cinco segundos', () => {
    render(<ConfirmationModal {...defaultProps} isLoading={true} />)
    expect(screen.getByText('Aguarde, por favor…')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(
      screen.getByText('A operação continua. Aguarde, por favor.')
    ).toBeInTheDocument()
  })

  it('usa variant para a cor do botão de confirmação', () => {
    render(<ConfirmationModal {...defaultProps} variant="warning" />)
    const confirmButton = screen.getByText('Confirmar')
    expect(confirmButton).toBeInTheDocument()
  })
})
