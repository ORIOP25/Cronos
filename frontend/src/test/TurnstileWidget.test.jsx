import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ContactQuestionnaire from '../features/contact/components/ContactQuestionnaire'
import { renderWithProviders } from './testUtils'

const contactMutation = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  reset: vi.fn(),
}))

vi.mock('../features/contact/data', () => ({
  useSubmitContact: () => contactMutation,
}))

function advanceToMessageStep() {
  fireEvent.click(screen.getByRole('button', { name: 'Começar' }))
  fireEvent.click(screen.getByRole('button', { name: /Outro/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Entre 1 e 5' }))
  fireEvent.click(screen.getByRole('button', { name: 'Entre 1 e 15' }))
  fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText(/Email/), { target: { value: 'ana@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
}

describe('Turnstile widget lifecycle', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_TURNSTILE_SITE_KEY', 'test-site-key')
    contactMutation.mutateAsync.mockReset()
    contactMutation.reset.mockReset()
    contactMutation.mutateAsync.mockResolvedValue(undefined)
    window.turnstile = {
      render: vi.fn(() => 'widget-id'),
      remove: vi.fn(),
      reset: vi.fn(),
    }
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    delete window.turnstile
  })

  it('renders once and removes only on unmount when inputs change', async () => {
    const { unmount } = renderWithProviders(<ContactQuestionnaire />)
    advanceToMessageStep()

    await waitFor(() => expect(window.turnstile.render).toHaveBeenCalledTimes(1))
    const callbacks = window.turnstile.render.mock.calls[0][1]
    fireEvent.change(screen.getByLabelText('Mensagem, opcional'), { target: { value: 'Detalhes' } })

    await waitFor(() => expect(window.turnstile.render).toHaveBeenCalledTimes(1))
    act(() => callbacks.callback('token'))
    expect(window.turnstile.remove).not.toHaveBeenCalled()
    expect(window.turnstile.render).toHaveBeenCalledTimes(1)

    unmount()
    expect(window.turnstile.remove).toHaveBeenCalledTimes(1)
  })

  it('submits the token and ignores a double submit while pending', async () => {
    contactMutation.mutateAsync.mockImplementation(() => new Promise(() => {}))
    const { unmount } = renderWithProviders(<ContactQuestionnaire />)
    advanceToMessageStep()
    await waitFor(() => expect(window.turnstile.render).toHaveBeenCalledTimes(1))
    act(() => window.turnstile.render.mock.calls[0][1].callback('token'))

    const form = screen.getByRole('button', { name: 'Pedir demonstração' }).closest('form')
    fireEvent.submit(form)
    fireEvent.submit(form)

    await waitFor(() => expect(contactMutation.mutateAsync).toHaveBeenCalledTimes(1))
    expect(contactMutation.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ turnstile_token: 'token' }))
    unmount()
  })

  it('clears the token and resets the widget after an API failure', async () => {
    contactMutation.mutateAsync.mockRejectedValueOnce(new Error('API down'))
    renderWithProviders(<ContactQuestionnaire />)
    advanceToMessageStep()
    await waitFor(() => expect(window.turnstile.render).toHaveBeenCalledTimes(1))
    act(() => window.turnstile.render.mock.calls[0][1].callback('token'))
    fireEvent.click(screen.getByRole('button', { name: 'Pedir demonstração' }))

    await waitFor(() => expect(window.turnstile.reset).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
