import { act, useState } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SmartTable from '../components/SmartTable'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const deleteErrorWithCode = (status, code) => Object.assign(new Error('Falha da API'), {
  response: { status, data: { detail: { code } } },
})

describe('SmartTable', () => {
  afterEach(() => {
    resetClerkState()
  })

  it('does not open a row when its native controls receive clicks or keyboard input', () => {
    const row = { id: 1, name: 'A' }
    const open = vi.fn()
    render(<SmartTable columns={[{ key: 'note', label: 'Nota', render: () => <input aria-label="Nota da linha" /> }]} data={[row]} onRowClick={open} getRowLabel={(item) => `Abrir ${item.name}`} />)
    const input = screen.getByRole('textbox', { name: 'Nota da linha' })
    fireEvent.click(input)
    fireEvent.keyDown(input, { key: ' ' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(open).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('row', { name: 'Abrir A' }))
    expect(open).toHaveBeenCalledExactlyOnceWith(row)
  })

  it('ignores a removal that resolves after the organization changed', async () => {
    let resolveDelete
    const onDelete = vi.fn(() => new Promise((resolve) => { resolveDelete = resolve }))
    setClerkState({ isSignedIn: true, userId: 'user_a', orgId: 1 })
    const renderTable = () => (
      <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 4, name: 'Sala E' }]} actions onEdit={vi.fn()} onDelete={onDelete} />
    )
    const { rerender } = renderWithProviders(renderTable(), { withToaster: true })

    fireEvent.click(screen.getByRole('button', { name: /remover sala e/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))

    act(() => { setClerkState({ orgId: 2 }) })
    rerender(renderTable())
    await act(async () => { resolveDelete({ remove_effect: 'hard_delete' }) })

    expect(document.querySelector('[data-rht-toaster]')).toBeEmptyDOMElement()
  })

  it('renders columns and calls edit and async delete callbacks', async () => {
    const row = { id: 7, name: 'Sala 7' }
    const onEdit = vi.fn()
    const onDelete = vi.fn().mockResolvedValue(undefined)

    render(
      <SmartTable
        columns={[{ key: 'name', label: 'Nome', render: (item) => item.name.toUpperCase() }]}
        data={[row]}
        actions
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    )

    expect(screen.getByText('SALA 7')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Editar'))
    expect(onEdit).toHaveBeenCalledWith(row)

    fireEvent.click(screen.getByTitle('Remover'))
    fireEvent.click(await screen.findByRole('button', { name: 'Remover' }))
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(7))
  })

  it('keeps deletion pending until the promise resolves', async () => {
    let resolveDelete
    const onDelete = vi.fn(() => new Promise((resolve) => { resolveDelete = resolve }))
    render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'Sala A' }]} actions onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: /remover sala a/i }))
    const confirm = screen.getByRole('button', { name: 'Remover' })
    fireEvent.click(confirm)
    expect(screen.getByRole('button', { name: /a remover/i })).toBeDisabled()
    resolveDelete()
    await waitFor(() => expect(screen.queryByRole('button', { name: /a guardar/i })).not.toBeInTheDocument())
  })

  it('keeps the attempt recoverable and reports a transient failure once', async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error('Falha de rede'))
    renderWithProviders(
      <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 2, name: 'Sala B' }]} actions onEdit={vi.fn()} onDelete={onDelete} />,
      { withToaster: true },
    )
    fireEvent.click(screen.getByRole('button', { name: /remover sala b/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))

    expect(await screen.findByText(/não foi possível remover/i)).toBeInTheDocument()
    expect(within(document.querySelector('[data-rht-toaster]')).getAllByText(/não foi possível remover/i)).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Remover' })).toBeEnabled()
  })

  it('keeps a business block in context instead of a toast', async () => {
    const onDelete = vi.fn().mockRejectedValue(deleteErrorWithCode(409, 'resource_in_use'))
    renderWithProviders(
      <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 2, name: 'Sala B' }]} actions onEdit={vi.fn()} onDelete={onDelete} />,
      { withToaster: true },
    )
    fireEvent.click(screen.getByRole('button', { name: /remover sala b/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))

    expect(await screen.findByText(/utilizado no horário atual/i)).toBeInTheDocument()
    expect(document.querySelector('[data-rht-toaster]')).toBeEmptyDOMElement()
  })

  it('explains when the record is archived and history is preserved', async () => {
    const onDelete = vi.fn().mockResolvedValue({ remove_effect: 'archive' })
    renderWithProviders(
      <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 5, name: 'Sala C' }]} actions onEdit={vi.fn()} onDelete={onDelete} />,
      { withToaster: true },
    )
    fireEvent.click(screen.getByRole('button', { name: /remover sala c/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
    const toastHost = document.querySelector('[data-rht-toaster]')
    expect(await within(toastHost).findByText(/arquivado/i)).toBeInTheDocument()
    expect(within(toastHost).getByText(/histórico/i)).toBeInTheDocument()
  })

  it('confirms a physical removal', async () => {
    const onDelete = vi.fn().mockResolvedValue({ remove_effect: 'hard_delete' })
    renderWithProviders(
      <SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 6, name: 'Sala D' }]} actions onEdit={vi.fn()} onDelete={onDelete} />,
      { withToaster: true },
    )
    fireEvent.click(screen.getByRole('button', { name: /remover sala d/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))
    expect(await within(document.querySelector('[data-rht-toaster]')).findByText('Registo removido.')).toBeInTheDocument()
  })

  it('keeps the confirmation visible when the table becomes empty', async () => {
    const row = { id: 9, name: 'Última sala' }
    function ListPage() {
      const [rows, setRows] = useState([row])
      return (
        <SmartTable
          columns={[{ key: 'name', label: 'Nome' }]}
          data={rows}
          actions
          onEdit={vi.fn()}
          onDelete={async () => { setRows([]); return { remove_effect: 'hard_delete' } }}
        />
      )
    }
    renderWithProviders(<ListPage />, { withToaster: true })
    fireEvent.click(screen.getByRole('button', { name: /remover última sala/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remover' }))

    expect(await within(document.querySelector('[data-rht-toaster]')).findByText('Registo removido.')).toBeInTheDocument()
    expect(await screen.findByText(/ainda sem registos/i)).toBeInTheDocument()
  })

  it('builds the removal message from the row when deleteMessage is a function', () => {
    const deleteMessage = vi.fn((row) => `Remover ${row.name}?`)
    render(
      <SmartTable
        columns={[{ key: 'name', label: 'Nome' }]}
        data={[{ id: 8, name: 'Sala F' }]}
        actions
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        deleteMessage={deleteMessage}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /remover sala f/i }))

    expect(screen.getByText('Remover Sala F?')).toBeInTheDocument()
    expect(deleteMessage).toHaveBeenLastCalledWith(expect.objectContaining({ id: 8, name: 'Sala F' }))
  })

  it('activates labeled rows with Enter and Space', () => {
    const row = { id: 3, name: 'Curso A' }
    const onRowClick = vi.fn()
    render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[row]} onRowClick={onRowClick} getRowLabel={(item) => `Abrir ${item.name}`} />)
    const interactiveRow = screen.getByRole('row', { name: 'Abrir Curso A' })
    expect(interactiveRow).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(interactiveRow, { key: 'Enter' })
    fireEvent.keyDown(interactiveRow, { key: ' ' })
    expect(onRowClick).toHaveBeenCalledTimes(2)
    expect(onRowClick).toHaveBeenLastCalledWith(row)
  })
})
