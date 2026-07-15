import { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import { CAlert, CBadge, CButton, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBan, cilCheckCircle, cilList, cilWarning } from '@coreui/icons'
import { useScheduleDiff } from '../../hooks/useSchoolData'

const CHANGE_LABELS = {
  ADDED: 'Adicionado',
  MOVED: 'Movido',
  CHANGED: 'Alterado',
  REMOVED: 'Removido',
  UNCHANGED_IMPACTED: 'Sem alteração',
}

const DraftPanel = ({ draft, onApprove, onReject, isApproving, isRejecting }) => {
  const [showDiff, setShowDiff] = useState(false)
  const { data: diff = [], isLoading } = useScheduleDiff(draft.draft_id, showDiff)
  const counts = useMemo(() => diff.reduce((result, row) => ({
    ...result,
    [row.change_type]: (result[row.change_type] || 0) + 1,
  }), {}), [diff])
  const isWorking = isApproving || isRejecting
  const isPartial = draft.result_category === 'PARTIAL_RECOVERY'

  return (
    <CAlert color="warning" className="border border-warning mb-4">
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-3">
        <div className="flex-grow-1">
          <div className="fw-bold mb-2">
            <CIcon icon={cilWarning} className="me-2" />
            Rascunho pendente
          </div>
          <div className="d-flex flex-wrap gap-2 mb-3">
            <CBadge color="primary">{draft.strategy === 'ADAPTIVE_REPAIR' ? 'Reparação' : 'Primeiro horário'}</CBadge>
            <CBadge color={isPartial ? 'warning' : 'success'}>
              {isPartial ? 'Recuperação parcial' : 'Resultado completo'}
            </CBadge>
            {draft.recovery_escalation_level && (
              <CBadge color="secondary">{draft.recovery_escalation_level}</CBadge>
            )}
            {draft.adaptation_level && (
              <CBadge color="secondary">{draft.adaptation_level}</CBadge>
            )}
          </div>

          <div className="d-flex flex-wrap gap-4 small mb-3">
            <span><strong>{draft.changed_blocks}</strong> blocos alterados</span>
            <span><strong>{draft.affected_classes}</strong> turmas</span>
            <span><strong>{draft.affected_teachers}</strong> professores</span>
            <span><strong>{draft.affected_days}</strong> dias</span>
            <span><strong>{draft.disruption_score}</strong> perturbação</span>
          </div>

          {(draft.debt_hours_before > 0 || isPartial) && (
            <div className="small mb-3">
              <strong>{draft.debt_hours_recovered}h</strong> recuperadas de{' '}
              <strong>{draft.debt_hours_before}h</strong>;{' '}
              <strong>{draft.debt_hours_remaining}h</strong> por agendar.
            </div>
          )}

          {isPartial && (
            <div className="border-start border-3 border-warning ps-3 mb-3">
              <div className="fw-semibold">Bloqueio principal</div>
              <div className="small mb-2">{draft.main_blocker_message}</div>
              <div className="fw-semibold small">Ações recomendadas</div>
              <ul className="small mb-0 ps-3">
                {draft.recommended_actions.map(action => <li key={action}>{action}</li>)}
              </ul>
            </div>
          )}

          {draft.workload_override_used && (
            <CAlert color="danger" className="mb-3" data-testid="deadline-rescue-warning">
              <div className="fw-bold">Resgate de prazo com sobrecarga</div>
              <div className="small">
                Para recuperar as horas antes do prazo, este rascunho excede o limite confortável em{' '}
                {draft.class_overload_count || 0} dia(s) de turma ({draft.class_overload_excess_minutes || 0} min) e{' '}
                {draft.teacher_overload_count || 0} dia(s) de professor ({draft.teacher_overload_excess_minutes || 0} min).
              </div>
            </CAlert>
          )}

          {draft.warnings.map(warning => (
            <div key={warning} className="small text-warning-emphasis mb-1">{warning}</div>
          ))}

          <CButton
            color="secondary"
            variant="ghost"
            size="sm"
            className="px-0 mt-1"
            onClick={() => setShowDiff(value => !value)}
          >
            <CIcon icon={cilList} className="me-1" />
            {showDiff ? 'Ocultar alterações' : 'Ver alterações'}
          </CButton>

          {showDiff && (
            <div className="mt-3">
              {isLoading ? <CSpinner size="sm" /> : (
                <>
                  <div className="d-flex flex-wrap gap-2 mb-2">
                    {Object.entries(counts).map(([type, count]) => (
                      <CBadge color="light" textColor="dark" key={type}>
                        {CHANGE_LABELS[type] || type}: {count}
                      </CBadge>
                    ))}
                  </div>
                  <div className="d-flex flex-column gap-2">
                    {diff.map(row => (
                      <div key={row.id} className="small border-top pt-2">
                        <strong>{CHANGE_LABELS[row.change_type] || row.change_type}</strong>
                        {' · '}Turma {row.class_id} · Disciplina {row.subject_id}
                        {row.reason_message ? <div className="text-muted">{row.reason_message}</div> : null}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="d-flex gap-2">
          <CButton
            color="danger"
            variant="outline"
            size="sm"
            disabled={isWorking}
            onClick={() => onReject(draft.draft_id)}
          >
            {isRejecting ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilBan} className="me-1" />}
            Rejeitar
          </CButton>
          <CButton
            color="success"
            size="sm"
            disabled={isWorking || !draft.can_approve}
            onClick={() => onApprove(draft.draft_id)}
          >
            {isApproving ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilCheckCircle} className="me-1" />}
            Aprovar
          </CButton>
        </div>
      </div>
    </CAlert>
  )
}

DraftPanel.propTypes = {
  draft: PropTypes.shape({
    draft_id: PropTypes.number.isRequired,
    strategy: PropTypes.string.isRequired,
    result_category: PropTypes.string.isRequired,
    recovery_escalation_level: PropTypes.string,
    adaptation_level: PropTypes.string,
    debt_hours_before: PropTypes.number.isRequired,
    debt_hours_recovered: PropTypes.number.isRequired,
    debt_hours_remaining: PropTypes.number.isRequired,
    changed_blocks: PropTypes.number.isRequired,
    affected_classes: PropTypes.number.isRequired,
    affected_teachers: PropTypes.number.isRequired,
    affected_days: PropTypes.number.isRequired,
    disruption_score: PropTypes.number.isRequired,
    main_blocker_message: PropTypes.string,
    recommended_actions: PropTypes.arrayOf(PropTypes.string).isRequired,
    warnings: PropTypes.arrayOf(PropTypes.string).isRequired,
    can_approve: PropTypes.bool.isRequired,
    workload_override_used: PropTypes.bool,
    class_overload_count: PropTypes.number,
    class_overload_excess_minutes: PropTypes.number,
    teacher_overload_count: PropTypes.number,
    teacher_overload_excess_minutes: PropTypes.number,
  }).isRequired,
  onApprove: PropTypes.func.isRequired,
  onReject: PropTypes.func.isRequired,
  isApproving: PropTypes.bool,
  isRejecting: PropTypes.bool,
}

export default DraftPanel
