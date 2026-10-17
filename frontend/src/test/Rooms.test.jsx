import { fireEvent, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Rooms from '../pages/Rooms'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({
  rooms: vi.fn(),
  deleteRoom: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useRooms: () => hooks.rooms(),
  useCreateRoom: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateRoom: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteRoom: () => ({ mutateAsync: hooks.deleteRoom }),
  useRoomTypes: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateRoomType: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateRoomType: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteRoomType: () => ({ isPending: false, mutateAsync: vi.fn() }),
}))

const normalType = { id: 1, name: 'Normal', is_normal: true }

const createRoom = (overrides) => ({
  id: 1,
  name: 'Sala C4',
  capacity: 30,
  is_archived: false,
  room_type: normalType,
  home_classes: [],
  ...overrides,
})

describe('Rooms removal', () => {
  beforeEach(() => {
    hooks.deleteRoom.mockReset().mockResolvedValue({ remove_effect: 'hard_delete' })
  })

  it('names the home classes that become Automática when a home room is removed', () => {
    hooks.rooms.mockReturnValue({
      data: [createRoom({ home_classes: [{ id: 11, name: '10.º A' }, { id: 12, name: '10.º B' }] })],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    renderWithRouter(<Rooms />)

    fireEvent.click(screen.getByRole('button', { name: 'Remover Sala C4' }))

    expect(screen.getByText(/Essas turmas passam a Automática\./)).toHaveTextContent(
      'É a sala da turma de 10.º A e 10.º B. Essas turmas passam a Automática.',
    )
  })

  it('keeps the removal message unchanged for a room that is no class home room', () => {
    hooks.rooms.mockReturnValue({
      data: [createRoom({ home_classes: [] })],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    renderWithRouter(<Rooms />)

    fireEvent.click(screen.getByRole('button', { name: 'Remover Sala C4' }))

    expect(screen.getByText(/Remover esta sala\?/)).toBeInTheDocument()
    expect(screen.queryByText(/passam a Automática/)).toBeNull()
  })
})
