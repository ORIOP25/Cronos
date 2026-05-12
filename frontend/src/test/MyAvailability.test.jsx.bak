import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import MyAvailability from '../pages/MyAvailability'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'
import apiClient from '../apiClient'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

const baseTimeslots = [
  {
    id: 1,
    day_of_week: 0,
    start_time: '08:00:00',
  },
]

const renderPage = () => renderWithProviders(<MyAvailability />)

describe('MyAvailability page (Ponto 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'teacher@escola.pt',
        role: 'teacher',
        teacherId: 42,
        orgId: 1,
      },
    })
  })

  it('carrega preferência já gravada no arranque', async () => {
    apiClient.get.mockResolvedValueOnce({ data: baseTimeslots })
    apiClient.get.mockResolvedValueOnce({
      data: [{ timeslot_id: 1, score: 2 }],
    })

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('A carregar grelha...')).not.toBeInTheDocument()
    })

    expect(screen.getAllByRole('button', { name: 'Preferencial' })).toHaveLength(2)
  })

  it('sobrescreve estado anterior sem duplicação no payload de save', async () => {
    apiClient.get.mockResolvedValueOnce({ data: baseTimeslots })
    apiClient.get.mockResolvedValueOnce({
      data: [{ timeslot_id: 1, score: 2 }],
    })
    apiClient.post.mockResolvedValueOnce({ data: { status: 'success', count: 1 } })

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('A carregar grelha...')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Impossível' }))
    fireEvent.click(screen.getByTitle('Impossível: Segunda às 08:00:00'))

    fireEvent.click(screen.getByRole('button', { name: 'Evitar' }))
    fireEvent.click(screen.getByTitle('Evitar: Segunda às 08:00:00'))

    fireEvent.click(screen.getByRole('button', { name: 'Guardar Alterações' }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/teachers/42/availability', [
        { timeslot_id: 1, score: 0 },
      ])
    })
  })

  it.each([
    [403, 'Sem permissões para gravar disponibilidade desta conta.'],
    [404, 'Perfil de professor não encontrado na organização autenticada.'],
    [400, 'Dados de disponibilidade inválidos. Atualize a página e tente novamente.'],
  ])('mapeia erro HTTP %s para feedback operacional de save', async (status, expectedMessage) => {
    apiClient.get.mockResolvedValueOnce({ data: baseTimeslots })
    apiClient.get.mockResolvedValueOnce({ data: [] })
    apiClient.post.mockRejectedValueOnce({ response: { status } })

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('A carregar grelha...')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Guardar Alterações' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(expectedMessage)
    })
  })

  it('apresenta erro operacional correto quando leitura inicial devolve 403', async () => {
    apiClient.get.mockResolvedValueOnce({ data: baseTimeslots })
    apiClient.get.mockRejectedValueOnce({ response: { status: 403 } })

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Sem permissões para consultar preferências de disponibilidade.'
      )
    })
  })

  it('mantém botão desativado durante gravação', async () => {
    apiClient.get.mockResolvedValueOnce({ data: baseTimeslots })
    apiClient.get.mockResolvedValueOnce({ data: [] })

    let resolveSave
    const savePromise = new Promise((resolve) => {
      resolveSave = resolve
    })
    apiClient.post.mockReturnValueOnce(savePromise)

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('A carregar grelha...')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Guardar Alterações' }))

    expect(screen.getByRole('button', { name: 'A guardar...' })).toBeDisabled()

    resolveSave({ data: { status: 'success', count: 0 } })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Guardar Alterações' })).not.toBeDisabled()
    })
  })
})
