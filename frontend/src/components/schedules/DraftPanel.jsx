import PropTypes from 'prop-types'
import { CAlert, CSpinner, CButton } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilBan, cilCheckCircle } from '@coreui/icons'
import { useScheduleDiff } from '../../hooks/useSchoolData'

const DraftPanel = ({ draft, onApprove, onReject, isApproving, isRejecting }) => {
  const { data: diff, isLoading } = useScheduleDiff(draft.generation_id)
  const isWorking = isApproving || isRejecting

  return (
    <CAlert color="warning" className="border border-warning mb-4">
      <div className="d-flex align-items-start justify-content-between flex-wrap gap-3">
        <div>
          <div className="fw-bold mb-1">
            <CIcon icon={cilWarning} className="me-2" />
            Rascunho de Reparação Pendente
          </div>
          <div className="text-muted small mb-2">
            Geração{' '}<code>{draft.generation_id.substring(0, 8)}…</code>
            {draft.earliest_date && (
              <span>{' '}·{' '}{draft.earliest_date} → {draft.latest_date}</span>
            )}
          </div>
          {isLoading && <CSpinner size="sm" />}
          {!isLoading && diff && (
            <div className="d-flex flex-column gap-2 mt-3">
              <div className="d-flex gap-3 flex-wrap">
                <span className="badge bg-success-subtle text-success border border-success">
                  +{diff.added} aulas adicionadas
                </span>
                <span className="badge bg-danger-subtle text-danger border border-danger">
                  -{diff.removed} aulas removidas
                </span>
                <span className="badge bg-secondary-subtle text-secondary border border-secondary">
                  {diff.unchanged} sem alterações
                </span>
              </div>
              {diff.statistics && (
                <div className="bg-white p-2 rounded border small text-muted">
                  <strong>Resumo (vs Atual):</strong>
                  <div className="d-flex flex-wrap gap-4 mt-2">
                    <div>
                      <div><strong>{diff.statistics.delta_projected_end_date_days > 0 ? '+' : ''}{diff.statistics.delta_projected_end_date_days} dias</strong></div>
                      <div style={{ fontSize: '0.75rem' }}>Fim das aulas</div>
                    </div>
                    <div>
                      <div><strong>{diff.statistics.backlog_remaining_hours}h</strong></div>
                      <div style={{ fontSize: '0.75rem' }}>Por agendar</div>
                    </div>
                    <div>
                      <div><strong>{diff.statistics.aggregate_gap_variation > 0 ? '+' : ''}{diff.statistics.aggregate_gap_variation}</strong></div>
                      <div style={{ fontSize: '0.75rem' }}>Furos</div>
                    </div>
                    <div>
                      <div><strong>{(diff.statistics.churn_outside_frozen_ratio * 100).toFixed(1)}%</strong></div>
                      <div style={{ fontSize: '0.75rem' }}>Alterações (futuro)</div>
                    </div>
                    <div>
                      <div><strong>{diff.statistics.end_date_spread_days} dias</strong></div>
                      <div style={{ fontSize: '0.75rem' }}>Dispersão fim</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="d-flex gap-2 align-self-center">
          <CButton
            color="danger" variant="outline" size="sm"
            disabled={isWorking}
            onClick={() => { onReject(draft.generation_id) }}
          >
            {isRejecting
              ? <CSpinner size="sm" className="me-1" />
              : <CIcon icon={cilBan} className="me-1" />
            }
            Rejeitar
          </CButton>
          <CButton
            color="success" size="sm"
            disabled={isWorking}
            onClick={() => { onApprove(draft.generation_id) }}
          >
            {isApproving
              ? <CSpinner size="sm" className="me-1" />
              : <CIcon icon={cilCheckCircle} className="me-1" />
            }
            Aprovar e Ativar
          </CButton>
        </div>
      </div>
    </CAlert>
  )
}

DraftPanel.propTypes = {
  draft: PropTypes.shape({
    generation_id: PropTypes.string.isRequired,
    count:         PropTypes.number,
    earliest_date: PropTypes.string,
    latest_date:   PropTypes.string,
  }).isRequired,
  onApprove:   PropTypes.func.isRequired,
  onReject:    PropTypes.func.isRequired,
  isApproving: PropTypes.bool,
  isRejecting: PropTypes.bool,
}

export default DraftPanel
