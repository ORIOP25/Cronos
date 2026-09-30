import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import { useScheduleTaskStatus } from '../features/scheduling/data'

vi.mock('../features/scheduling/data', () => ({
  useScheduleTaskStatus: vi.fn(),
}))

describe('GenerationStatusPanel', () => {
  afterEach(cleanup)

  it.each([
    ['CANCELLED', 'Geração cancelada'],
    ['FAILED', 'Não foi possível concluir a geração'],
    ['STALE', 'Os dados mudaram durante a geração'],
    ['INFEASIBLE', 'Não é possível colocar todas as aulas com estas condições'],
    ['INCONCLUSIVE', 'Não foi possível concluir a pesquisa'],
  ])('shows a clear terminal message for %s', (status, expected) => {
    useScheduleTaskStatus.mockReturnValue({ data: { status } })

    render(<GenerationStatusPanel jobId={12} />)

    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('explains that an inconclusive search is not an impossibility', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'INCONCLUSIVE' } })

    render(<GenerationStatusPanel jobId={13} />)

    expect(screen.getByText(/não significa que o horário seja impossível/i)).toBeInTheDocument()
  })

  it('shows an honest queue position without fake progress', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'QUEUED', queue_position: 3, queued_at: new Date().toISOString() },
    })

    render(<GenerationStatusPanel jobId={14} />)

    expect(screen.getByText(/posição 3 na fila/i)).toBeInTheDocument()
  })

  it('offers a retry when loading the job fails temporarily', () => {
    const refetch = vi.fn()
    useScheduleTaskStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { status: 503 } },
      refetch,
    })

    render(<GenerationStatusPanel jobId={15} />)

    screen.getByRole('button', { name: /tentar novamente/i }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('links to login for an expired session without retry looping', () => {
    useScheduleTaskStatus.mockReturnValue({
      isLoading: false,
      isError: true,
      error: { response: { status: 401 } },
      refetch: vi.fn(),
    })

    render(<GenerationStatusPanel jobId={16} />)

    expect(screen.getByRole('link', { name: /entrar novamente/i })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).toBeNull()
  })

  it('shows access guidance for forbidden status without retry', () => {
    useScheduleTaskStatus.mockReturnValue({
      isLoading: false,
      isError: true,
      error: { response: { status: 403 } },
      refetch: vi.fn(),
    })

    render(<GenerationStatusPanel jobId={17} />)

    expect(screen.getByText(/não tem permissão/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).toBeNull()
  })

  it('keeps the success state when the job completes', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'SUCCEEDED' }, isLoading: false })

    render(<GenerationStatusPanel jobId={18} />)

    expect(screen.getByText(/proposta pronta/i)).toBeInTheDocument()
  })

  it('points to rooms when generation stopped for an incompatible room', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'NO_ELIGIBLE_ROOM' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={19} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /abrir salas/i })).toHaveAttribute('href', '/rooms')
  })
})
