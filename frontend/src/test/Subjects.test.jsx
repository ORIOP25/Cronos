import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Subjects from '../pages/Subjects'
import { renderWithRouter } from './testUtils'

const hooks = vi.hoisted(() => ({
  subjects: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../features/catalog/data', () => ({
  useSubjects: () => hooks.subjects(),
  useCreateSubject: () => hooks.create(),
  useUpdateSubject: () => hooks.update(),
  useDeleteSubject: () => hooks.remove(),
}))

const editSubject = {
  id: 1,
  name: 'Programação',
  required_room_type: 'lab',
  modules: [{ id: 11, name: 'Módulo 1', code: 'P1', hours_total: 25 }],
}

const mutationState = (mutateAsync) => ({
  mutateAsync,
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null,
})

const renderSubjects = () => renderWithRouter(<Subjects />, { withToaster: true })

const openEditAndAddModule = (moduleName) => {
  fireEvent.click(screen.getByRole('button', { name: 'Editar Programação' }))
  fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: moduleName } })
  fireEvent.change(screen.getByLabelText(/horas/i), { target: { value: '10' } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
  fireEvent.click(screen.getByRole('button', { name: /guardar disciplina/i }))
}

describe('Subjects', () => {
  beforeEach(() => {
    hooks.subjects.mockReset().mockReturnValue({
      data: [editSubject],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    hooks.create.mockReset().mockReturnValue(mutationState(vi.fn().mockResolvedValue({ id: 2 })))
    hooks.update.mockReset().mockReturnValue(mutationState(vi.fn().mockResolvedValue({ id: 1 })))
    hooks.remove.mockReset().mockReturnValue(mutationState(vi.fn().mockResolvedValue(undefined)))
  })

  it('warns that new modules stay unselected when editing an existing subject', async () => {
    renderSubjects()

    openEditAndAddModule('Módulo novo')

    const toaster = document.querySelector('[data-rht-toaster]')
    expect(await within(toaster).findByText(/os módulos novos não foram marcados nas turmas/i)).toBeInTheDocument()
    expect(within(toaster).queryByText(/^Disciplina atualizada\.$/)).not.toBeInTheDocument()
    expect(hooks.update.mock.results[0].value.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({
      id: 1,
      modules: expect.arrayContaining([expect.objectContaining({ name: 'Módulo novo', order: 1 })]),
    }))
  })

  it('keeps the plain success message when creating a new subject', async () => {
    renderSubjects()

    fireEvent.click(screen.getByRole('button', { name: /nova disciplina/i }))
    fireEvent.change(screen.getByLabelText(/nome da disciplina/i), { target: { value: 'Matemática' } })
    fireEvent.change(screen.getByLabelText(/nome do módulo/i), { target: { value: 'Módulo A' } })
    fireEvent.change(screen.getByLabelText(/horas/i), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    fireEvent.click(screen.getByRole('button', { name: /guardar disciplina/i }))

    const toaster = document.querySelector('[data-rht-toaster]')
    expect(await within(toaster).findByText('Disciplina criada.')).toBeInTheDocument()
    expect(within(toaster).queryByText(/não foram marcados nas turmas/i)).not.toBeInTheDocument()
    await waitFor(() => expect(hooks.create.mock.results[0].value.mutateAsync).toHaveBeenCalled())
  })
})
