import { act } from 'react'
import { screen } from '@testing-library/react'
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { toast } from 'react-hot-toast'
import App from '../App'
import { TutorialShell } from '../features/tutorial/TutorialShell'
import { renderWithProviders, renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

vi.mock('../components/DefaultLayout', () => ({
  default: ({ children }) => children,
}))

describe('feedback context boundaries', () => {
  beforeEach(() => {
    resetClerkState()
  })

  afterEach(() => {
    resetClerkState()
  })

  it('removes messages from the previous organization when the context changes', async () => {
    setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
    window.history.replaceState({}, '', '/')
    const { rerender } = renderWithProviders(<App />, { withToaster: true })

    act(() => { toast.success('Mensagem da organização anterior.') })
    expect(await screen.findByText('Mensagem da organização anterior.')).toBeInTheDocument()

    act(() => { setClerkState({ orgId: 2 }) })
    rerender(<App />)

    expect(screen.queryByText('Mensagem da organização anterior.')).not.toBeInTheDocument()
  })

  it('removes simulated messages when the guide context ends', () => {
    const { unmount } = renderWithRouter(
      <TutorialShell activeNavItem="/dashboard">
        <div>Conteúdo simulado</div>
      </TutorialShell>,
      { withToaster: true },
    )

    act(() => { toast.success('Aula registada.') })
    expect(screen.getByText('Aula registada.')).toBeInTheDocument()

    unmount()
    expect(screen.queryByText('Aula registada.')).not.toBeInTheDocument()
  })
})
