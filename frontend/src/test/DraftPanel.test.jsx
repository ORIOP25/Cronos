import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DraftPanel from '../components/schedules/DraftPanel'
import { useScheduleDiff } from '../features/scheduling/data'

vi.mock('../features/scheduling/data', () => ({
  useScheduleDiff: vi.fn(),
}))

const proposal = {
  proposal_id: 42,
  status: 'PENDING',
  strategy: 'ADAPTIVE_RECOVERY',
  is_stale: false,
  stale_reason: null,
  can_approve: true,
  warnings: [],
  metrics: {
    changed_lessons: 3,
    disruption_cost: 14,
    excess_days: 0,
    margin_days: 6,
  },
  quality_summary: {
    stop_reason: 'ROUND_LIMIT',
    objective_scope: 'ANNUAL',
    certified_stages: 2,
    total_stages: 5,
    claims_optimum: false,
    policy_version: 'baseline-v1',
  },
}

const diff = {
  is_first_generation: false,
  physical: [
    { change_type: 'ADDED', lesson_id: 1, class_id: 7, subject_id: 9, before: null, after: { date: '2025-09-23' } },
  ],
  modular: [],
  counts: { added: 1, moved: 0, removed: 0, room_changed: 0, modular_updates: 0 },
}

describe('DraftPanel', () => {
  afterEach(cleanup)

  beforeEach(() => {
    useScheduleDiff.mockImplementation((_proposalId, enabled) => ({
      data: enabled ? diff : undefined,
      isLoading: false,
    }))
  })

  it('renders the proposal summary without fetching the diff detail', () => {
    const onApprove = vi.fn()
    render(
      <DraftPanel
        draft={proposal}
        onApprove={onApprove}
        onReject={vi.fn()}
        isApproving={false}
        isRejecting={false}
      />
    )

    expect(screen.getByText('Proposta pendente')).toBeInTheDocument()
    expect(screen.getByText('Atualização do horário')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(useScheduleDiff).toHaveBeenLastCalledWith(42, false)

    fireEvent.click(screen.getByRole('button', { name: 'Aprovar' }))
    expect(onApprove).toHaveBeenCalledWith(42)
  })

  it('loads detailed changes only when requested', () => {
    render(
      <DraftPanel
        draft={proposal}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        isApproving={false}
        isRejecting={false}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ver alterações' }))

    expect(useScheduleDiff).toHaveBeenLastCalledWith(42, true)
    expect(screen.getByText('Adicionado: 1')).toBeInTheDocument()
  })

  it('blocks approval for a stale proposal and explains why', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, is_stale: true, stale_reason: 'REVISIONS_CHANGED', can_approve: false }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByTestId('stale-proposal-warning')).toHaveTextContent(/alterações mais recentes/i)
    expect(screen.getByRole('button', { name: 'Aprovar' })).toBeDisabled()
  })

  it('shows the certified quality scope without claiming a global optimum', () => {
    render(
      <DraftPanel
        draft={proposal}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )
    expect(screen.getByTestId('quality-certification')).toHaveTextContent(
      /Qualidade certificada em 2 de 5 etapas/i
    )
  })

  it('shows the certified optimum only when every stage is proven', () => {
    render(
      <DraftPanel
        draft={{
          ...proposal,
          quality_summary: { ...proposal.quality_summary, certified_stages: 5, claims_optimum: true },
        }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )
    expect(screen.getByTestId('quality-certification')).toHaveTextContent(
      /Qualidade certificada dentro do âmbito calculado/i
    )
  })

  it('keeps the preference-excess alert visible while it exists', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, excess_days: 2 } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )
    expect(screen.getByTestId('deadline-excess-warning')).toHaveTextContent(
      /depois da data preferencial/i
    )
  })
})
