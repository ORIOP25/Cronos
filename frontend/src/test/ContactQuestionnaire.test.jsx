import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from './testUtils'

const { mutation } = vi.hoisted(() => ({ mutation: { mutateAsync: vi.fn(), reset: vi.fn(), isPending: false } }))
vi.mock('../features/contact/data', () => ({ useSubmitContact: () => mutation }))

import ContactQuestionnaire from '../components/marketing/ContactQuestionnaire'

async function reachFinalStep() {
  fireEvent.click(screen.getByRole('button', { name: /Falar com a nossa equipa/ }))
  fireEvent.click(screen.getByRole('button', { name: /Criar horários/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 5/ }))
  fireEvent.click(screen.getByRole('button', { name: /Entre 1 e 15/ }))
  fireEvent.change(screen.getByLabelText('O seu nome *'), { target: { value: 'Ana Coordenadora' } })
  fireEvent.change(screen.getByLabelText('Endereço de email *'), { target: { value: 'ana@escola.pt' } })
  fireEvent.change(screen.getByLabelText('Número de telefone'), { target: { value: '+351 912 345 678' } })
  fireEvent.submit(screen.getByRole('heading', { name: 'Dados de contacto' }).closest('form'))
  fireEvent.change(screen.getByPlaceholderText(/qualquer detalhe/), { target: { value: 'Demonstração' } })
}

describe('ContactQuestionnaire', () => {
  beforeEach(() => { mutation.mutateAsync.mockReset(); mutation.reset.mockReset(); mutation.isPending = false })

  it('posts the complete payload and confirms only after success', async () => {
    mutation.mutateAsync.mockResolvedValue(undefined)
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    fireEvent.click(screen.getByRole('button', { name: /^Enviar/ }))
    await waitFor(() => expect(mutation.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ courses: 'Entre 1 e 5', teachers: 'Entre 1 e 15', name: 'Ana Coordenadora', email: 'ana@escola.pt', phone: '+351 912 345 678', website: '' })))
    expect(document.querySelector('.cronos-contact-step--success')).toBeInTheDocument()
  })

  it('keeps the data and presents retry guidance on failure', async () => {
    const requestError = new Error('request failed')
    requestError.response = { status: 429, data: { detail: {} } }
    mutation.mutateAsync.mockRejectedValue(requestError)
    renderWithProviders(<ContactQuestionnaire />)
    await reachFinalStep()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^Enviar/ })); await Promise.resolve() })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Foram efetuadas v?rias tentativas'))
    expect(screen.getByPlaceholderText(/qualquer detalhe/)).not.toHaveValue('')
    expect(screen.getByRole('link', { name: 'email' })).toHaveAttribute('href', 'mailto:contacto@cronos.pt')
  })
})
