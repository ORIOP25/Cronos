import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Subjects from '../pages/Subjects'
import { renderWithRouter } from './testUtils'

const NEW_MODULE_WARNING = 'Disciplina atualizada. Os módulos novos não foram marcados nas turmas. Marque-os nas turmas que os vão ter.'

const { useSubjectsMock, useRoomTypesMock, createSubjectMock, updateSubjectMock } = vi.hoisted(() => ({
  useSubjectsMock: vi.fn(),
  useRoomTypesMock: vi.fn(),
  createSubjectMock: vi.fn(),
  updateSubjectMock: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useSubjects: () => useSubjectsMock(),
  useRoomTypes: () => useRoomTypesMock(),
  useCreateSubject: () => ({ isPending: false, mutateAsync: createSubjectMock }),
  useUpdateSubject: () => ({ isPending: false, mutateAsync: updateSubjectMock }),
  useDeleteSubject: () => ({ isPending: false, mutateAsync: vi.fn() }),
}))

const existingSubject = {
  id: 1,
  name: 'Programação',
  room_type: { id: 11, name: 'Normal', is_normal: true },
  modules: [{ id: 11, name: 'M1', code: 'C1', hours_total: 25, order: 0 }],
}

const toastRegion = () => within(document.querySelector('[data-rht-toaster]'))

const addModule = (name, hours) => {
  fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: name } })
  fireEvent.change(screen.getByLabelText(/horas/i), { target: { value: hours } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
}

describe('Subjects new-module warning', () => {
  beforeEach(() => {
    useSubjectsMock.mockReturnValue({
      data: [existingSubject],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    useRoomTypesMock.mockReturnValue({ data: [{ id: 11, name: 'Normal', is_normal: true }], isLoading: false, isError: false, refetch: vi.fn() })
    createSubjectMock.mockReset()
    createSubjectMock.mockResolvedValue({})
    updateSubjectMock.mockReset()
    updateSubjectMock.mockResolvedValue({})
  })

  it('shows exactly one warning when an edit adds a module without an id', async () => {
    renderWithRouter(<Subjects />, { withToaster: true })

    expect(screen.getByRole('columnheader', { name: 'Tipo de sala' })).toBeInTheDocument()
    expect(screen.getByText('Normal')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /editar programação/i }))
    addModule('M2', '30')
    fireEvent.click(screen.getByRole('button', { name: /guardar alterações/i }))

    expect(await toastRegion().findByText(NEW_MODULE_WARNING)).toBeInTheDocument()
    expect(toastRegion().getAllByRole('status')).toHaveLength(1)
    expect(updateSubjectMock).toHaveBeenCalledWith({
      id: 1,
      name: 'Programação',
      room_type_id: 11,
      modules: [
        { id: 11, name: 'M1', code: 'C1', hours_total: 25, order: 0 },
        { name: 'M2', code: '', hours_total: 30, order: 1 },
      ],
    })
  })

  it('keeps the plain toast when the edit only touches existing modules', async () => {
    renderWithRouter(<Subjects />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: /editar programação/i }))
    fireEvent.click(screen.getByRole('button', { name: /editar M1/i }))
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: 'M1 atualizado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    fireEvent.click(screen.getByRole('button', { name: /guardar alterações/i }))

    expect(await toastRegion().findByText('Disciplina atualizada.')).toBeInTheDocument()
    expect(toastRegion().queryByText(/não foram marcados nas turmas/i)).not.toBeInTheDocument()
    expect(toastRegion().getAllByRole('status')).toHaveLength(1)
  })

  it('does not warn when a new subject is created with a module', async () => {
    renderWithRouter(<Subjects />, { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: /nova disciplina/i }))
    fireEvent.change(screen.getByLabelText(/nome da disciplina/i), { target: { value: 'Matemática' } })
    addModule('M1', '25')
    fireEvent.click(screen.getByRole('button', { name: /criar disciplina/i }))

    expect(await toastRegion().findByText('Disciplina criada.')).toBeInTheDocument()
    expect(toastRegion().queryByText(/não foram marcados nas turmas/i)).not.toBeInTheDocument()
    expect(toastRegion().getAllByRole('status')).toHaveLength(1)
  })
})
