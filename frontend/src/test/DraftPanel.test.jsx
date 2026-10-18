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

  it('marks a joint lesson in the proposal diff', () => {
    useScheduleDiff.mockImplementation(() => ({
      data: {
        ...diff,
        physical: [{ ...diff.physical[0], joint_class_ids: [7, 8] }],
      },
      isLoading: false,
    }))

    render(
      <DraftPanel
        draft={proposal}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ver alterações' }))

    expect(screen.getByText('Conjunta')).toBeInTheDocument()
  })

  it('shows the avoidable room changes next to the other metrics', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, avoidable_room_changes: 3 } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByText(/mudanças de sala evitáveis/)).toHaveTextContent('3 mudanças de sala evitáveis')
  })

  it('uses the singular for one avoidable room change', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, avoidable_room_changes: 1 } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByText(/mudança de sala evitável/)).toHaveTextContent('1 mudança de sala evitável')
    expect(screen.queryByText(/mudanças de sala evitáveis/)).toBeNull()
  })

  it('shows the home-room misses and the preference cost in hours', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, home_room_misses: 2, preference_cost_minutes: 90 } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByText(/aulas fora da sala da turma/)).toHaveTextContent('2 aulas fora da sala da turma')
    expect(screen.getByText(/em blocos a evitar/)).toHaveTextContent('1,5 h em blocos a evitar')
  })

  it('uses the singular for one home-room miss', () => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, home_room_misses: 1 } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByText(/aula fora da sala da turma/)).toHaveTextContent('1 aula fora da sala da turma')
    expect(screen.queryByText(/aulas fora da sala da turma/)).toBeNull()
  })

  it.each([
    [60, '1 h'],
    [0, '0 h'],
  ])('formats %i preference minutes as %s', (minutes, expected) => {
    render(
      <DraftPanel
        draft={{ ...proposal, metrics: { ...proposal.metrics, preference_cost_minutes: minutes } }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByText(/em blocos a evitar/)).toHaveTextContent(`${expected} em blocos a evitar`)
  })

  it('hides the home-room misses and the preference cost on an outdated proposal', () => {
    render(
      <DraftPanel
        draft={{
          ...proposal,
          is_stale: true,
          stale_reason: 'REVISIONS_CHANGED',
          can_approve: false,
          metrics: { ...proposal.metrics, home_room_misses: 2, preference_cost_minutes: 90 },
        }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByTestId('stale-proposal-warning')).toBeInTheDocument()
    expect(screen.queryByText(/aulas fora da sala da turma/)).toBeNull()
    expect(screen.queryByText(/em blocos a evitar/)).toBeNull()
  })

  it('omits the home-room and preference metrics when the proposal does not report them', () => {
    render(
      <DraftPanel
        draft={proposal}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.queryByText(/aulas? fora da sala da turma/)).toBeNull()
    expect(screen.queryByText(/em blocos a evitar/)).toBeNull()
  })

  it('hides the avoidable room changes on an outdated proposal', () => {
    render(
      <DraftPanel
        draft={{
          ...proposal,
          is_stale: true,
          stale_reason: 'REVISIONS_CHANGED',
          can_approve: false,
          metrics: { ...proposal.metrics, avoidable_room_changes: 3 },
        }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )

    expect(screen.getByTestId('stale-proposal-warning')).toBeInTheDocument()
    expect(screen.queryByText(/mudanças de sala evitáveis/)).toBeNull()
  })
})
