import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import apiClient from '../apiClient'
import { resetClerkState, setClerkState } from './setup'
import { renderWithProviders, renderWithRouter } from './testUtils'
import RoomTypesModal from '../components/RoomTypesModal'
import Rooms from '../pages/Rooms'

vi.mock('../apiClient', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

const NORMAL = { id: 11, name: 'Normal', is_normal: true, room_count: 3, subject_count: 2 }
const WORKSHOP = { id: 24, name: 'Oficina', is_normal: false, room_count: 1, subject_count: 0 }

const apiError = (status, detail) => Object.assign(new Error('Request failed'), {
  response: { status, data: { detail } },
})

const renderModal = () => renderWithProviders(<RoomTypesModal onClose={vi.fn()} />)

const rowFor = (name) => screen.getByRole('cell', { name }).closest('tr')

describe('RoomTypesModal', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ orgId: 'org-a', isSignedIn: true, isLoaded: true })
    vi.clearAllMocks()
    apiClient.get.mockResolvedValue([NORMAL, WORKSHOP])
    apiClient.post.mockResolvedValue({ id: 30, name: 'Oficina', is_normal: false, room_count: 0, subject_count: 0 })
    apiClient.patch.mockResolvedValue({ ...WORKSHOP, name: 'Oficina Técnica' })
    apiClient.delete.mockResolvedValue({ message: 'Tipo de sala removido com sucesso', remove_effect: 'hard_delete' })
  })

  it('shows Normal as fixed without actions and offers edit and remove for custom types', async () => {
    renderModal()

    const normalRow = within(await screen.findByRole('table')).getByText('Normal').closest('tr')
    expect(within(normalRow).getByText('Fixo')).toBeInTheDocument()
    expect(within(normalRow).queryByRole('button')).not.toBeInTheDocument()

    const workshopRow = rowFor('Oficina')
    expect(within(workshopRow).getByRole('button', { name: 'Editar Oficina' })).toBeInTheDocument()
    expect(within(workshopRow).getByRole('button', { name: 'Remover Oficina' })).toBeInTheDocument()
  })

  it('creates a type by name with POST and refreshes the list', async () => {
    apiClient.get
      .mockResolvedValueOnce([NORMAL, WORKSHOP])
      .mockResolvedValueOnce([NORMAL, WORKSHOP, { id: 30, name: 'Oficina Nova', is_normal: false, room_count: 0, subject_count: 0 }])
    renderModal()
    await screen.findByRole('table')

    fireEvent.change(screen.getByLabelText('Nome do tipo de sala'), { target: { value: 'Oficina Nova' } })
    fireEvent.click(screen.getByRole('button', { name: 'Novo tipo' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/room-types/', { name: 'Oficina Nova' }))
    expect(await screen.findByRole('cell', { name: 'Oficina Nova' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })

  it('shows the duplicate-name message when the server refuses a new type', async () => {
    apiClient.post.mockRejectedValue(apiError(409, { code: 'room_type_name_taken', message: 'technical detail' }))
    renderModal()
    await screen.findByRole('table')

    fireEvent.change(screen.getByLabelText('Nome do tipo de sala'), { target: { value: 'oficina' } })
    fireEvent.click(screen.getByRole('button', { name: 'Novo tipo' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/^Já existe um tipo de sala com este nome\.$/)
    expect(screen.getByLabelText('Nome do tipo de sala')).toHaveAttribute('aria-invalid', 'true')
  })

  it('renames a custom type with PATCH', async () => {
    renderModal()
    await screen.findByRole('table')

    fireEvent.click(within(rowFor('Oficina')).getByRole('button', { name: 'Editar Oficina' }))
    const input = screen.getByLabelText('Nome do tipo de sala')
    expect(input).toHaveValue('Oficina')
    fireEvent.change(input, { target: { value: 'Oficina Técnica' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar nome' }))

    await waitFor(() => expect(apiClient.patch).toHaveBeenCalledWith('/room-types/24', { name: 'Oficina Técnica' }))
  })

  it('shows the fixed-type message when the server refuses a rename', async () => {
    apiClient.patch.mockRejectedValue(apiError(409, { code: 'room_type_fixed', message: 'technical detail' }))
    renderModal()
    await screen.findByRole('table')

    fireEvent.click(within(rowFor('Oficina')).getByRole('button', { name: 'Editar Oficina' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar nome' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'O tipo Normal é fixo: não pode mudar de nome nem ser removido.',
    )
  })

  it('names the rooms and subjects that block the removal of a type in use', async () => {
    apiClient.delete.mockRejectedValue(apiError(409, {
      code: 'resource_in_use',
      message: 'technical detail',
      context: { rooms: ['C4', 'Lab 2'], subjects: ['Oficina I'] },
    }))
    renderModal()
    await screen.findByRole('table')

    fireEvent.click(within(rowFor('Oficina')).getByRole('button', { name: 'Remover Oficina' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith('/room-types/24'))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Este tipo é usado por: salas C4 e Lab 2; disciplinas Oficina I. Mude-lhes o tipo primeiro.',
    )
  })

  it('does not call the API for an empty name and explains the length limit', async () => {
    renderModal()
    await screen.findByRole('table')

    fireEvent.click(screen.getByRole('button', { name: 'Novo tipo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escreva um nome de tipo com até 60 caracteres.')
    expect(apiClient.post).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Nome do tipo de sala'), { target: { value: 'x'.repeat(61) } })
    fireEvent.click(screen.getByRole('button', { name: 'Novo tipo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escreva um nome de tipo com até 60 caracteres.')
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('opens from the Rooms page with the admin button', async () => {
    apiClient.get.mockImplementation((url) => Promise.resolve(url === '/rooms/' ? [] : [NORMAL, WORKSHOP]))
    renderWithRouter(<Rooms />)

    fireEvent.click(await screen.findByRole('button', { name: 'Tipos de sala' }))

    expect(await screen.findByRole('dialog', { name: 'Tipos de sala' })).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'Oficina' })).toBeInTheDocument()
  })
})
