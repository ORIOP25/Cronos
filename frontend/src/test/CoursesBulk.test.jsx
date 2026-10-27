import { fireEvent, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import Courses from '../pages/Courses'
import { renderWithRouter } from './testUtils'
const { remove } = vi.hoisted(() => ({ remove: vi.fn().mockResolvedValue({}) }))
vi.mock('../features/catalog/data', () => ({
  useCourses: () => ({ data: [{ id: 1, name: 'Curso A' }, { id: 2, name: 'Curso B' }] }),
  useCreateCourse: () => ({ mutate: vi.fn() }),
  useDeleteCourse: () => ({ mutateAsync: remove }),
}))
it('removes selected courses after confirmation', async () => {
  renderWithRouter(<Courses />)
  fireEvent.click(screen.getByTitle('Selecionar Curso A'))
  expect(screen.getByRole('checkbox', { name: 'Selecionar Curso A' })).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  expect(remove).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  await waitFor(() => expect(remove).toHaveBeenCalledWith(1))
  expect(remove).not.toHaveBeenCalledWith(2)
})
