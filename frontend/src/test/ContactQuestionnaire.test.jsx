import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from './testUtils'

const { mutation } = vi.hoisted(() => ({ mutation: { mutateAsync: vi.fn(), reset: vi.fn(), isPending: false } }))
vi.mock('../features/contact/data', () => ({ useSubmitContact: () => mutation }))
import ContactQuestionnaire from '../components/marketing/ContactQuestionnaire'

async function reachFinalStep() {
  fireEvent.click(screen.getByRole('button', { name: /Falar/ }))
  fireEvent.click(screen.getByRole('button', { name: /Criar/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 5/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 15/ }))
  fireEvent.change(screen.getByLabelText(/nome/), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText(/email/), { target: { value: 'ana@escola.pt' } })
  fireEvent.submit(screen.getByRole('heading', { name: /Dados/ }).closest('form'))
  const form = screen.getByRole('heading', { name: /Mais/ }).closest('form')
  const token = document.createElement('input')
  token.name = 'cf-turnstile-response'
  token.value = 'token'
  form.append(token)
}

describe('ContactQuestionnaire', () => {
  beforeEach(() => { mutation.mutateAsync.mockReset(); mutation.reset.mockReset(); mutation.isPending = false })

  it('submits the Turnstile token and shows success only after the request succeeds', async () => {
    mutation.mutateAsync.mockResolvedValue(undefined)
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    await waitFor(() => expect(mutation.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ name: 'Ana', website: '', turnstileToken: 'token' })))
    expect(document.querySelector('.cronos-contact-step--success')).toBeInTheDocument()
  })

  it('blocks a missing token and preserves the fallback after failure', async () => {
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    document.querySelector('[name="cf-turnstile-response"]').remove()
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    expect(mutation.mutateAsync).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('anti-spam')
    mutation.mutateAsync.mockRejectedValue({ response: { status: 429, data: { detail: {} } } })
    const token = document.createElement('input')
    token.name = 'cf-turnstile-response'
    token.value = 'token'
    screen.getByRole('heading', { name: /Mais/ }).closest('form').append(token)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^Enviar/ })); await Promise.resolve() })
    await waitFor(() => expect(screen.getByRole('link', { name: 'email' })).toHaveAttribute('href', 'mailto:contacto@cronos.pt'))
  })
})
