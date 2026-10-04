import { act, useState } from 'react'
import { CButton, CModal, CModalBody, CModalHeader, CModalTitle } from '@coreui/react'
import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'react-hot-toast'
import { renderWithProviders } from './testUtils'

function ModalHarness({ onClose }) {
  return (
    <CModal visible onClose={onClose} keyboard>
      <CModalHeader>
        <CModalTitle>Registo de aula</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <CButton onClick={() => toast.success('Registo guardado.')}>Guardar</CButton>
        <CButton onClick={() => toast.error('Não foi possível guardar. Tente novamente.')}>Falhar</CButton>
      </CModalBody>
    </CModal>
  )
}

function StatefulModal() {
  const [visible, setVisible] = useState(true)
  return (
    <div>
      {visible && <ModalHarness onClose={() => setVisible(false)} />}
      <span data-testid="modal-state">{visible ? 'open' : 'closed'}</span>
    </div>
  )
}

async function renderModal(ui) {
  await act(async () => {
    renderWithProviders(ui, { withToaster: true })
  })
  await act(async () => { vi.runOnlyPendingTimers() })
}

describe('feedback with a real CoreUI modal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    window.matchMedia = vi.fn(() => ({
      matches: true,
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
  })

  afterEach(() => {
    act(() => { toast.remove() })
    vi.useRealTimers()
  })

  it('announces a success over the open modal without moving focus', async () => {
    await renderModal(<ModalHarness onClose={vi.fn()} />)
    const saveButton = screen.getByRole('button', { name: 'Guardar' })
    saveButton.focus()

    await act(async () => { fireEvent.click(saveButton) })

    const toastHost = document.querySelector('[data-rht-toaster]')
    expect(toastHost).toHaveStyle({ zIndex: '9999' })
    expect(toastHost.closest('[aria-hidden="true"]')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('Registo guardado.')
    expect(document.activeElement).toBe(saveButton)
  })

  it('announces an error immediately while the modal stays open', async () => {
    await renderModal(<ModalHarness onClose={vi.fn()} />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Falhar' }))
    })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Não foi possível guardar. Tente novamente.')
    expect(alert.closest('[aria-hidden="true"]')).toBeNull()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('keeps the toast when Escape closes the modal', async () => {
    await renderModal(<StatefulModal />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    })
    expect(screen.getByRole('status')).toBeInTheDocument()

    await act(async () => {
      fireEvent.keyDown(document, { key: 'Escape' })
      vi.runOnlyPendingTimers()
    })

    expect(screen.getByTestId('modal-state')).toHaveTextContent('closed')
    expect(screen.getByRole('status')).toHaveTextContent('Registo guardado.')
  })
})
