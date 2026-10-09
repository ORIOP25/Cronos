import { act } from 'react'
import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { toast } from 'react-hot-toast'
import App from '../App'
import { TutorialShell } from '../features/tutorial/TutorialShell'
import { renderWithProviders, renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

vi.mock('../components/DefaultLayout', () => ({
  default: ({ children }) => children,
}))

// The feedback contract lives in App's storage-scope cleanup. The public
// marketing layout is unrelated and pulls in head metadata plus the signed-in
// redirect (and its member query). Isolate it so this fixture exercises only
// the feedback boundary.
vi.mock('../features/marketing/components/layout/MarketingLayout', () => ({
  default: () => null,
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
    const { rerender, container } = renderWithProviders(<App />, { withToaster: true })

    act(() => { toast.success('Mensagem da organização anterior.') })
    expect(await screen.findByText('Mensagem da organização anterior.')).toBeInTheDocument()
    await waitFor(() => expect(container.querySelector('.spinner-border')).not.toBeInTheDocument())

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
