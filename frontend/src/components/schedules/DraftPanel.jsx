import { useMemo, useState } from 'react'
import { CBadge, CButton, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBan, cilCheckCircle, cilList, cilWarning } from '@coreui/icons'
import { useScheduleDiff } from '../../features/scheduling/data'
import { SCHEDULE_PRIORITY_CRITERIA } from '../../features/schoolConfig/schedulePriorities'
import FeedbackBanner from '../FeedbackBanner'

// The finish date is a measure of the proposal, not a school criterion, so it is listed here only.
const FINISH_DATE_ROW = { key: 'finish_early', title: 'Data da última aula.' }
const PRIORITY_SUMMARY_ROWS = [FINISH_DATE_ROW, ...SCHEDULE_PRIORITY_CRITERIA]

const CHANGE_LABELS = {
  ADDED: 'Adicionado',
  MOVED: 'Movido',
  REMOVED: 'Removido',
  ROOM_CHANGED: 'Sala alterada',
}

const WARNING_LABELS = {
  COMPLETION_AFTER_PREFERENCE:
    'Algumas turmas terminam depois da data preferencial. O aviso mantém-se enquanto a situação existir.',
  SEARCH_INTERRUPTED:
    'A pesquisa foi interrompida pelo limite de segurança. A proposta é válida, mas pode ser possível melhorá-la.',
}

const avoidableRoomChangesLabel = (count) => (count === 1 ? 'mudança de sala evitável' : 'mudanças de sala evitáveis')
const homeRoomMissesLabel = (count) => (count === 1 ? 'aula fora da sala da turma' : 'aulas fora da sala da turma')
const preferenceHoursFormatter = new Intl.NumberFormat('pt-PT', { maximumFractionDigits: 1 })

const STALE_TEXT =
  'Existem alterações mais recentes. Esta proposta já não pode ser aprovada. Gere uma nova proposta.'

function changeSummary(diff) {
  const counts = diff?.counts || {}
  const rows = [
    ['added', 'Adicionado'],
    ['moved', 'Movido'],
    ['removed', 'Removido'],
    ['room_changed', 'Sala alterada'],
  ]
  return rows
    .filter(([key]) => Number(counts[key] || 0) > 0)
    .map(([key, label]) => `${label}: ${counts[key]}`)
}

function formatPriorityMeasure(key, value) {
  if (value == null) return '—'
  if (key === 'finish_early') return value
  if (key === 'teacher_gaps' || key === 'class_gaps'
    || key === 'teacher_preferences' || key === 'class_preferences') {
    return `${preferenceHoursFormatter.format(value / 60)} h`
  }
  if (key === 'subject_pace') {
    const days = preferenceHoursFormatter.format(value)
    return `${days} ${value === 1 ? 'dia' : 'dias'}`
  }
  return value
}

const DraftPanel = ({ draft, onApprove, onReject, isApproving, isRejecting, allowApprove = true, allowReject = true }) => {
  const [showDiff, setShowDiff] = useState(false)
  const proposalId = draft.proposal_id
  const { data: diff, isLoading } = useScheduleDiff(proposalId, showDiff)
  const metrics = draft.metrics || {}
  const prioritySummary = metrics.priority_summary
  const quality = draft.quality_summary || {}
  const certifiedStages = Number(quality.certified_stages ?? 0)
  const totalStages = Number(quality.total_stages ?? 0)
  const isWorking = isApproving || isRejecting
  const isFirstGeneration = diff?.is_first_generation === true
  const summaries = useMemo(() => changeSummary(diff), [diff])
  const stale = draft.is_stale || draft.status === 'STALE'
  const canApprove = allowApprove && draft.can_approve && !stale

  return (
    <section className="draft-panel mb-4" aria-label="Proposta pendente">
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-3">
        <div className="flex-grow-1">
          <div className="fw-bold mb-2">
            <CIcon icon={cilWarning} className="me-2" />
            Proposta pendente
          </div>
          <div className="d-flex flex-wrap gap-2 mb-3">
            <CBadge color="primary">
              {draft.strategy === 'ADAPTIVE_RECOVERY' ? 'Atualização do horário' : 'Primeiro horário'}
            </CBadge>
            {!stale && <CBadge color="success">Resultado completo</CBadge>}
            {stale && <CBadge color="danger">Desatualizada</CBadge>}
          </div>

          {stale ? (
            <div className="small mb-3" data-testid="stale-proposal-warning">{STALE_TEXT}</div>
          ) : (
            <div className="d-flex flex-wrap gap-4 small mb-3">
              <span><strong>{metrics.changed_lessons ?? 0}</strong> aulas alteradas</span>
              <span><strong>{metrics.disruption_cost ?? 0}</strong> perturbação</span>
              <span>
                <strong>{metrics.excess_days ?? 0}</strong> dias depois da data preferencial
              </span>
              <span><strong>{metrics.margin_days ?? 0}</strong> dias de margem</span>
              {typeof metrics.avoidable_room_changes === 'number' && (
                <span><strong>{metrics.avoidable_room_changes}</strong> {avoidableRoomChangesLabel(metrics.avoidable_room_changes)}</span>
              )}
              {typeof metrics.home_room_misses === 'number' && (
                <span><strong>{metrics.home_room_misses}</strong> {homeRoomMissesLabel(metrics.home_room_misses)}</span>
              )}
              {typeof metrics.preference_cost_minutes === 'number' && (
                <span>
                  <strong>{preferenceHoursFormatter.format(metrics.preference_cost_minutes / 60)} h</strong> em blocos a evitar
                </span>
              )}
            </div>
          )}

          {prioritySummary?.proposal && (
            <div className="table-responsive mb-3" data-testid="priority-summary">
              <table className="table table-sm align-middle" aria-label="Resumo das prioridades do horário">
                <thead>
                  <tr>
                    <th scope="col">Critério</th>
                    {prioritySummary.published && <th scope="col">Horário publicado</th>}
                    <th scope="col">Proposta</th>
                  </tr>
                </thead>
                <tbody>
                  {PRIORITY_SUMMARY_ROWS.map(({ key, title }) => (
                    <tr key={key}>
                      <th scope="row">{title}</th>
                      {prioritySummary.published && (
                        <td>{formatPriorityMeasure(key, prioritySummary.published[key])}</td>
                      )}
                      <td>{formatPriorityMeasure(key, prioritySummary.proposal[key])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {metrics.priorities_followed === false && (
            <div className="mb-3" data-testid="priority-fallback-warning">
              <FeedbackBanner tone="warning">
                Não foi possível seguir as prioridades definidas pela escola nesta proposta. Experimente baixar alguns critérios e gerar outra proposta.
              </FeedbackBanner>
            </div>
          )}

          {totalStages > 0 && (
            <div className="small text-muted mb-2" data-testid="quality-certification">
              {quality.claims_optimum
                ? 'Qualidade certificada dentro do âmbito calculado.'
                : `Qualidade certificada em ${certifiedStages} de ${totalStages} etapas.`}
            </div>
          )}

          {Number(metrics.excess_days || 0) > 0 && (
            <div className="mb-2" data-testid="deadline-excess-warning">
              <FeedbackBanner tone="danger">
                Algumas turmas terminam depois da data preferencial definida pela escola.
              </FeedbackBanner>
            </div>
          )}

          {(draft.warnings || []).map((warning) => (
            <div key={warning} className="small text-warning-emphasis mb-1">
              {WARNING_LABELS[warning] || 'Existem avisos sobre esta proposta.'}
            </div>
          ))}

          <CButton
            color="secondary"
            variant="ghost"
            size="sm"
            className="px-0 mt-1"
            onClick={() => setShowDiff(value => !value)}
            data-tutorial-target="review-schedule-changes"
          >
            <CIcon icon={cilList} className="me-1" />
            {showDiff ? 'Ocultar alterações' : 'Ver alterações'}
          </CButton>

          {showDiff && (
            <div className="mt-3">
              {isLoading ? <CSpinner size="sm" /> : (
                <>
                  <div className="d-flex flex-wrap gap-2 mb-2">
                    {isFirstGeneration && (
                      <CBadge color="light" textColor="dark">
                        Primeiro horário completo
                      </CBadge>
                    )}
                    {summaries.map(summary => (
                      <CBadge color="light" textColor="dark" key={summary}>{summary}</CBadge>
                    ))}
                    {Number(diff?.counts?.modular_updates || 0) > 0 && (
                      <CBadge color="light" textColor="dark">
                        Previsão modular atualizada: {diff.counts.modular_updates}
                      </CBadge>
                    )}
                  </div>
                  <div className="d-flex flex-column gap-2">
                    {(diff?.physical || []).map(row => (
                      <div key={`physical-${row.lesson_id}-${row.change_type}`} className="small border-top pt-2">
                        <strong>{CHANGE_LABELS[row.change_type] || 'Alteração'}</strong>
                        {' · '}Turma {row.class_id} · Disciplina {row.subject_id}
                        {row.before?.date && row.after?.date && row.before.date !== row.after.date
                          ? <span className="text-muted"> · {row.before.date} → {row.after.date}</span>
                          : null}
                        {Array.isArray(row.joint_class_ids) && row.joint_class_ids.length > 0 && (
                          <CBadge color="info" className="ms-1">Conjunta</CBadge>
                        )}
                      </div>
                    ))}
                    {(diff?.modular || []).slice(0, 20).map(row => (
                      <div key={`modular-${row.lesson_id}`} className="small border-top pt-2">
                        <strong>Previsão modular</strong>
                        {' · '}Turma {row.class_id} · Disciplina {row.subject_id}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="d-flex gap-2 ms-auto">
          {allowReject && <CButton
            color="danger"
            variant="outline"
            size="sm"
            disabled={isWorking}
            onClick={() => onReject(proposalId)}
          >
            {isRejecting ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilBan} className="me-1" />}
            Rejeitar
          </CButton>}
          {allowApprove && <CButton
            color="success"
            size="sm"
            disabled={isWorking || !canApprove}
            onClick={() => onApprove(proposalId)}
            data-tutorial-target="approve-schedule"
          >
            {isApproving ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilCheckCircle} className="me-1" />}
            Aprovar
          </CButton>}
        </div>
      </div>
    </section>
  )
}

export default DraftPanel
