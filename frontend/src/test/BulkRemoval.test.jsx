import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import SmartTable from '../components/SmartTable'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

it('shows contextual actions only after selecting records and lets the user clear them', () => {
  const remove = vi.fn()
  render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDelete={remove} />)
  expect(screen.queryByRole('button', { name: /remover selecionados/i })).not.toBeInTheDocument()
  const all = within(screen.getByRole('columnheader', { name: 'Seleção' })).getByRole('checkbox', { name: 'Selecionar todos' })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar A' }))
  expect(all).toBePartiallyChecked()
  expect(screen.getByRole('status')).toHaveTextContent('1 selecionado')
  fireEvent.click(screen.getByRole('button', { name: 'Limpar seleção' }))
  expect(all).not.toBePartiallyChecked()
  expect(screen.getByRole('checkbox', { name: 'Selecionar A' })).not.toBeChecked()
  expect(all).toHaveFocus()
  expect(screen.queryByRole('button', { name: /remover selecionados/i })).not.toBeInTheDocument()
  expect(remove).not.toHaveBeenCalled()
})

it('lists the selected records and preserves the selection when confirmation is cancelled', () => {
  const remove = vi.fn()
  render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDelete={remove} />)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar todos' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  const dialog = screen.getByRole('dialog')
  expect(within(dialog).getByRole('list', { name: 'Registos selecionados' })).toHaveTextContent('A')
  expect(within(dialog).getByRole('button', { name: 'Remover', exact: true })).toBeEnabled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
  expect(screen.getByRole('checkbox', { name: 'Selecionar A' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Selecionar B' })).toBeChecked()
  expect(remove).not.toHaveBeenCalled()
})

it('removes selected records after one confirmation and identifies failures', async () => {
  const remove = vi.fn().mockImplementation((id) => id === 2 ? Promise.reject(new Error('blocked')) : Promise.resolve())
  render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }, { id: 3, name: 'C' }]} actions onDelete={remove} />)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar A' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar B' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  expect(remove).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  await waitFor(() => expect(remove).toHaveBeenCalledTimes(2))
  expect(remove).toHaveBeenCalledWith(1)
  expect(remove).toHaveBeenCalledWith(2)
  expect(await screen.findByText(/B.*não foi possível/i)).toBeInTheDocument()
  expect(screen.getByRole('checkbox', { name: 'Selecionar A' })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Selecionar B' })).toBeChecked()
})

it('selects all displayed records and can clear the selection', () => {
  render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDelete={vi.fn()} />)
  const all = screen.getByRole('checkbox', { name: 'Selecionar todos' })
  fireEvent.click(all)
  expect(screen.getByRole('checkbox', { name: 'Selecionar A' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Selecionar B' })).toBeChecked()
  fireEvent.click(all)
  expect(screen.getByRole('checkbox', { name: 'Selecionar A' })).not.toBeChecked()
})

it('explains the consequences for each selected room before confirmation', () => {
  render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'Sala A' }, { id: 2, name: 'Sala B' }]} onDelete={vi.fn()} deleteMessage={(row) => `${row.name}: turmas passam a Automática.`} />)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar todos' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  expect(screen.getByText(/Sala A: turmas passam a Automática/)).toBeInTheDocument()
  expect(screen.getByText(/Sala B: turmas passam a Automática/)).toBeInTheDocument()
})

it('clears selection and failures on organization changes', async () => {
  setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
  const table = () => <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'Sala A' }]} onDelete={vi.fn().mockRejectedValue(new Error('failed'))} />
  const { rerender } = renderWithProviders(table())
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar Sala A' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  expect(await screen.findByText(/Sala A: Não foi possível remover/i)).toBeInTheDocument()
  act(() => setClerkState({ orgId: 2 }))
  rerender(table())
  expect(screen.queryByText(/Sala A: Não foi possível remover/i)).not.toBeInTheDocument()
  expect(screen.getByRole('checkbox', { name: 'Selecionar Sala A' })).not.toBeChecked()
  act(() => setClerkState({ orgId: 1 }))
  rerender(table())
  expect(screen.getByRole('checkbox', { name: 'Selecionar Sala A' })).not.toBeChecked()
  resetClerkState()
})

it('does not start further removals or unlock a new attempt after an organization change', async () => {
  let finishFirst, finishSecond
  const remove = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve })).mockImplementationOnce(() => new Promise((resolve) => { finishSecond = resolve }))
  setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
  const table = () => <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDelete={remove} />
  const { rerender } = renderWithProviders(table())
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar todos' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  act(() => setClerkState({ orgId: 2 }))
  rerender(table())
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar B' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  await act(async () => finishFirst())
  expect(remove).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button', { name: /a remover/i })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Limpar seleção' })).toBeDisabled()
  await act(async () => finishSecond())
  resetClerkState()
})

it('does not resume an old batch after leaving and returning to an organization', async () => {
  let finishFirst
  const remove = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve })).mockResolvedValue({})
  setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
  const table = () => <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'A' }, { id: 2, name: 'B' }]} onDelete={remove} />
  const { rerender } = renderWithProviders(table())
  fireEvent.click(screen.getByRole('checkbox', { name: 'Selecionar todos' }))
  fireEvent.click(screen.getByRole('button', { name: /remover selecionados/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
  act(() => setClerkState({ orgId: 2 }))
  rerender(table())
  act(() => setClerkState({ orgId: 1 }))
  rerender(table())
  await act(async () => finishFirst())
  expect(remove).toHaveBeenCalledTimes(1)
  resetClerkState()
})
