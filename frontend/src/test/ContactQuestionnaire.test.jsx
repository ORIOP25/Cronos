import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from './testUtils'

const { mutation } = vi.hoisted(() => ({ mutation: { mutateAsync: vi.fn(), reset: vi.fn(), isPending: false } }))
vi.mock('../features/contact/data', () => ({ useSubmitContact: () => mutation }))
import ContactQuestionnaire from '../components/marketing/ContactQuestionnaire'

let turnstileOptions

async function reachFinalStep({ waitForWidget = true } = {}) {
  fireEvent.click(screen.getByRole('button', { name: /Falar/ }))
  fireEvent.click(screen.getByRole('button', { name: /Criar/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 5/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 15/ }))
  fireEvent.change(screen.getByLabelText(/nome/), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText(/email/), { target: { value: 'ana@escola.pt' } })
  fireEvent.submit(screen.getByRole('heading', { name: /Dados/ }).closest('form'))
  if (waitForWidget) await waitFor(() => expect(window.turnstile.render).toHaveBeenCalled())
}

describe('ContactQuestionnaire', () => {
  beforeEach(() => {
    mutation.mutateAsync.mockReset()
    mutation.reset.mockReset()
    mutation.isPending = false
    vi.stubEnv('VITE_TURNSTILE_SITE_KEY', 'site-key')
    turnstileOptions = undefined
    window.turnstile = {
      render: vi.fn((element, options) => { turnstileOptions = options; return 'widget-id' }),
      reset: vi.fn(),
      remove: vi.fn(),
    }
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllEnvs()
    delete window.turnstile
  })

  it('waits for Turnstile to load after the first render and renders once', async () => {
    delete window.turnstile
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep({ waitForWidget: false })

    window.setTimeout(() => {
      window.turnstile = {
        render: vi.fn((element, options) => { turnstileOptions = options; return 'widget-id' }),
        reset: vi.fn(),
        remove: vi.fn(),
      }
    }, 20)

    await waitFor(() => expect(window.turnstile.render).toHaveBeenCalledTimes(1))
  })

  it('reports a safe error when Turnstile does not load in time', async () => {
    vi.useFakeTimers()
    delete window.turnstile
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep({ waitForWidget: false })

    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByRole('alert')).toHaveTextContent('NÃ£o foi possÃ­vel carregar a verificaÃ§Ã£o anti-spam.')
  })

  it('submits the current token using the snake_case public contract', async () => {
    mutation.mutateAsync.mockResolvedValue(undefined)
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    act(() => turnstileOptions.callback('valid-token'))
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    await waitFor(() => expect(mutation.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Ana', website: '', turnstile_token: 'valid-token',
    })))
    expect(screen.getByText(/Obrigado pelo contacto, Ana/)).toBeInTheDocument()
  })

  it('blocks submission without a token using the required Portuguese message', async () => {
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    expect(mutation.mutateAsync).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Confirme a verificação anti-spam antes de enviar o pedido.')
  })

  it('clears an expired token before submission', async () => {
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    act(() => {
      turnstileOptions.callback('expired-token')
      turnstileOptions['expired-callback']()
    })
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    expect(mutation.mutateAsync).not.toHaveBeenCalled()
  })

  it('resets Turnstile after backend failure and preserves questionnaire fields', async () => {
    mutation.mutateAsync.mockRejectedValue({ response: { status: 503, data: { detail: 'Indisponível.' } } })
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    act(() => turnstileOptions.callback('token'))
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    await waitFor(() => expect(window.turnstile.reset).toHaveBeenCalledWith('widget-id'))
    expect(screen.getByRole('link', { name: 'email' })).toHaveAttribute('href', 'mailto:contacto@cronos.pt')
    fireEvent.click(screen.getByRole('button', { name: /Voltar/ }))
    expect(screen.getByLabelText(/nome/)).toHaveValue('Ana')
  })

  it('clears the token and reports widget errors', async () => {
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    act(() => {
      turnstileOptions.callback('token')
      turnstileOptions['error-callback']()
    })
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    expect(mutation.mutateAsync).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('anti-spam')
  })
})
