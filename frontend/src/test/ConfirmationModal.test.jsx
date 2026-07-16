import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ConfirmationModal from '../components/ConfirmationModal'

describe('ConfirmationModal', () => {
  const defaultProps = {
    visible: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
  }

  it('mostra título e mensagem padrão', () => {
    render(<ConfirmationModal {...defaultProps} />)
    expect(screen.getByText('Confirmar Remoção')).toBeInTheDocument()
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

  it('usa variant para a cor do botão de confirmação', () => {
    render(<ConfirmationModal {...defaultProps} variant="warning" />)
    const confirmButton = screen.getByText('Confirmar')
    expect(confirmButton).toBeInTheDocument()
  })
})
