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

    expect(screen.getByText(/3\.º pedido em espera/i)).toBeInTheDocument()
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

  it('shows error feedback for a failed generation', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'FAILED' } })

    render(<GenerationStatusPanel jobId={20} />)

    expect(screen.getByTestId('generation-terminal')).toBeInTheDocument()
    expect(screen.getByText('Não foi possível concluir a geração')).toBeInTheDocument()
    expect(screen.getByText(/Ocorreu um erro durante a geração/)).toBeInTheDocument()
  })

  it('treats an unrecognized status as a generation failure', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'UNRECOGNIZED' } })

    render(<GenerationStatusPanel jobId={21} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Geração não iniciada')
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

  it('explains a joint lesson with no common free time from result_code', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'INFEASIBLE', result_code: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={22} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/não têm horas livres em comum/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /abrir configuração/i })).toHaveAttribute('href', '/config')
  })

  it('explains a joint lesson with no common free time from stop_reason', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={23} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/não têm horas livres em comum/i)).toBeInTheDocument()
  })

  it('keeps the generic infeasible message without a joint code', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'INFEASIBLE' }, isLoading: false })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={24} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Reveja disponibilidades, salas, professor atribuído ou datas/)).toBeInTheDocument()
    expect(screen.queryByText(/não têm horas livres em comum/i)).not.toBeInTheDocument()
  })

  it('keeps the stale message when the data changed during generation', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'STALE', stop_reason: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={26} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Os dados da escola mudaram durante a geração/)).toBeInTheDocument()
    expect(screen.queryByText(/não têm horas livres em comum/i)).not.toBeInTheDocument()
  })

  it('points to rooms when a joint lesson lacks a compatible room', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'JOINT_ROOM_CAPACITY' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={25} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /abrir salas/i })).toHaveAttribute('href', '/rooms')
  })
})
