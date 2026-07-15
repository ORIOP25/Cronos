import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DraftPanel from '../components/schedules/DraftPanel'
import { useScheduleDiff } from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', () => ({
  useScheduleDiff: vi.fn(),
}))

const draft = {
  draft_id: 42,
  strategy: 'ADAPTIVE_REPAIR',
  result_category: 'PARTIAL_RECOVERY',
  recovery_escalation_level: 'DEADLINE_RESCUE',
  adaptation_level: null,
  debt_hours_before: 18,
  debt_hours_recovered: 8,
  debt_hours_remaining: 10,
  changed_blocks: 3,
  affected_classes: 2,
  affected_teachers: 2,
  affected_days: 2,
  disruption_score: 14,
  main_blocker_message: 'The remaining hours cannot fit with the current resources and hard end date.',
  recommended_actions: ['Add compatible resources.', 'Generate the schedule again.'],
  warnings: ['Partial recovery generated.'],
  can_approve: true,
}

describe('DraftPanel', () => {
  afterEach(cleanup)

  beforeEach(() => {
    useScheduleDiff.mockImplementation((_draftId, enabled) => ({
      data: enabled ? [{
        id: 1,
        change_type: 'ADDED',
        class_id: 7,
        subject_id: 9,
        reason_message: 'A new target block was added.',
      }] : [],
      isLoading: false,
    }))
  })

  it('renders an approvable partial summary without fetching mandatory diff detail', () => {
    const onApprove = vi.fn()
    render(
      <DraftPanel
        draft={draft}
        onApprove={onApprove}
        onReject={vi.fn()}
        isApproving={false}
        isRejecting={false}
      />
    )

    expect(screen.getByText('Recuperação parcial')).toBeInTheDocument()
    expect(screen.getByText(/^8h$/)).toBeInTheDocument()
    expect(screen.getByText(draft.main_blocker_message)).toBeInTheDocument()
    expect(screen.queryByText('A new target block was added.')).not.toBeInTheDocument()
    expect(useScheduleDiff).toHaveBeenLastCalledWith(42, false)

    fireEvent.click(screen.getByRole('button', { name: 'Aprovar' }))
    expect(onApprove).toHaveBeenCalledWith(42)
  })

  it('loads detailed changes only when requested', () => {
    render(
      <DraftPanel
        draft={draft}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        isApproving={false}
        isRejecting={false}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ver alterações' }))

    expect(useScheduleDiff).toHaveBeenLastCalledWith(42, true)
    expect(screen.getByText('A new target block was added.')).toBeInTheDocument()
    expect(screen.getByText('Adicionado: 1')).toBeInTheDocument()
  })

  it('renders the deadline rescue workload override prominently', () => {
    render(
      <DraftPanel
        draft={{
          ...draft,
          workload_override_used: true,
          class_overload_count: 1,
          class_overload_excess_minutes: 60,
          teacher_overload_count: 2,
          teacher_overload_excess_minutes: 120,
        }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    )
    expect(screen.getByTestId('deadline-rescue-warning')).toHaveTextContent('Resgate de prazo com sobrecarga')
    expect(screen.getByTestId('deadline-rescue-warning')).toHaveTextContent('120 min')
  })
})
