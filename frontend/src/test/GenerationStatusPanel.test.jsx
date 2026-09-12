import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import { useScheduleTaskStatus } from '../features/scheduling/data'

vi.mock('../features/scheduling/data', () => ({
  useScheduleTaskStatus: vi.fn(),
}))

describe('GenerationStatusPanel', () => {
  afterEach(cleanup)

  it.each([
    ['NO_VALID_OUTPUT', 'Não foi possível gerar um horário válido'],
    ['CANCELED', 'Geração cancelada'],
    ['FAILED', 'Erro na geração'],
  ])('shows a clear terminal message for %s', (jobStatus, expected) => {
    useScheduleTaskStatus.mockReturnValue({ data: { job_status: jobStatus } })

    render(<GenerationStatusPanel jobId={12} />)

    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('shows the server failure detail for a timed-out job', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        job_status: 'FAILED',
        failure_code: 'TIMED_OUT',
        failure_message: 'A geração excedeu o limite de cinco minutos.',
      },
    })

    render(<GenerationStatusPanel jobId={13} />)

    expect(screen.getByText(/excedeu o limite de cinco minutos/i)).toBeInTheDocument()
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

    render(<GenerationStatusPanel jobId={14} />)

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

    render(<GenerationStatusPanel jobId={15} />)

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

    render(<GenerationStatusPanel jobId={16} />)

    expect(screen.getByText(/não tem permissão/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).toBeNull()
  })

  it('keeps the success state when the job completes', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { job_status: 'SUCCEEDED' }, isLoading: false })

    render(<GenerationStatusPanel jobId={17} />)

    expect(screen.getByText(/rascunho pronto/i)).toBeInTheDocument()
  })
})
