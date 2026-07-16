import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SmartTable from '../components/SmartTable'

describe('SmartTable', () => {
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
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(7))
  })

  it('keeps deletion pending until the promise resolves', async () => {
    let resolveDelete
    const onDelete = vi.fn(() => new Promise((resolve) => { resolveDelete = resolve }))
    render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 1, name: 'Sala A' }]} actions onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: /remover sala a/i }))
    const confirm = screen.getByRole('button', { name: 'Confirmar' })
    fireEvent.click(confirm)
    expect(screen.getByRole('button', { name: /a guardar/i })).toBeDisabled()
    resolveDelete()
    await waitFor(() => expect(screen.queryByRole('button', { name: /a guardar/i })).not.toBeInTheDocument())
  })

  it('keeps the confirmation recoverable when deletion rejects', async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error('Falha de rede'))
    render(<SmartTable columns={[{ key: 'name', label: 'Nome' }]} data={[{ id: 2, name: 'Sala B' }]} actions onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: /remover sala b/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText(/não foi possível remover/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeEnabled()
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
