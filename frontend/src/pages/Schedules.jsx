import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner, CButton,
  CFormSelect, CFormLabel, CRow, CCol, CProgress,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilCheckCircle, cilBan, cilWarning,
} from '@coreui/icons'
import {
  useTimeslots, useDrafts, useScheduleDiff, useApproveDraft,
  useRejectDraft, useGenerateSchedule, useScheduleTaskStatus,
} from '../hooks/useSchoolData'
import TimeGrid from '../components/TimeGrid'

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------
const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible', 'REVOKED']
const isPending = (status) => !!status && !TERMINAL_STATUSES.some(s => status.includes(s))

// ---------------------------------------------------------------------------
// Painel de Rascunho com Diff
// ---------------------------------------------------------------------------
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
              <span>
                {' '}·{' '}{draft.earliest_date} → {draft.latest_date}
              </span>
            )}
          </div>

          {isLoading ? (
            <CSpinner size="sm" />
          ) : diff && (
            <div className="d-flex gap-3 flex-wrap">
              <span className="badge bg-success-subtle text-success border border-success">
                +{diff.added} blocos adicionados
              </span>
              <span className="badge bg-danger-subtle text-danger border border-danger">
                -{diff.removed} blocos removidos
              </span>
              <span className="badge bg-secondary-subtle text-secondary border border-secondary">
                {diff.unchanged} sem alteração
              </span>
            </div>
          )}
        </div>

        <div className="d-flex gap-2 align-self-center">
          <CButton
            color="danger"
            variant="outline"
            size="sm"
            disabled={isWorking}
            onClick={() => { void onReject(draft.generation_id) }}
          >
            {isRejecting ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilBan} className="me-1" />}
            Rejeitar
          </CButton>
          <CButton
            color="success"
            size="sm"
            disabled={isWorking}
            onClick={() => { void onApprove(draft.generation_id) }}
          >
            {isApproving ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilCheckCircle} className="me-1" />}
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
    count: PropTypes.number,
    earliest_date: PropTypes.string,
    latest_date: PropTypes.string,
  }).isRequired,
  onApprove: PropTypes.func.isRequired,
  onReject: PropTypes.func.isRequired,
  isApproving: PropTypes.bool,
  isRejecting: PropTypes.bool,
}

// ---------------------------------------------------------------------------
// Painel de Estado da Geração
// ---------------------------------------------------------------------------
const GenerationStatusPanel = ({ taskId }) => {
  const { data: taskData } = useScheduleTaskStatus(taskId)

  if (!taskData) {
    return (
      <CAlert color="info" className="d-flex align-items-center gap-2">
        <CSpinner size="sm" />
        A aguardar resposta do servidor…
      </CAlert>
    )
  }

  const status = taskData.status ?? ''
  const isRunning = isPending(status)
  const result = taskData.result

  let alertColor = 'info'
  if (status.includes('SUCCESS') || status.includes('Success')) alertColor = 'success'
  if (status.includes('FAILURE') || status.includes('Error') || status.includes('Impossible')) alertColor = 'danger'

  const statusLabels = {
    PENDING: 'A aguardar worker…',
    FETCHING: 'A ler dados da escola…',
    SOLVING: 'CP-SAT a otimizar (pode demorar alguns minutos)…',
    EXPANDING: 'A expandir para datas reais…',
    SAVING: 'A guardar solução…',
    SUCCESS: 'Concluído!',
    FAILURE: 'Erro na geração.',
  }

  const label = statusLabels[status] ?? status

  return (
    <CAlert color={alertColor} className="mb-4">
      <div className="d-flex align-items-center gap-2 mb-2">
        {isRunning && <CSpinner size="sm" />}
        <strong>{label}</strong>
      </div>
      {isRunning && <CProgress animated value={100} className="mb-2" style={{ height: '4px' }} />}
      {result?.is_draft && (
        <div className="small mt-1">
          Rascunho criado com{' '}<strong>{result.count}</strong>{' '}blocos.
          Reveja o diff abaixo e aprove ou rejeite.
        </div>
      )}
      {result?.mode === 'full' && result?.count && (
        <div className="small mt-1">
          Horário ativo atualizado com{' '}<strong>{result.count}</strong>{' '}blocos.
        </div>
      )}
      {typeof result === 'string' && result.includes('preflight') && (
        <div className="small mt-1 text-danger">{result}</div>
      )}
    </CAlert>
  )
}

GenerationStatusPanel.propTypes = {
  taskId: PropTypes.string.isRequired,
}

// ---------------------------------------------------------------------------
// Painel de Erros de Preflight
// ---------------------------------------------------------------------------
const PreflightErrorPanel = ({ problems }) => (
  <CAlert color="danger" className="mb-4">
    <strong>Não é possível gerar o horário — pré-validação falhou:</strong>
    <ul className="mb-0 mt-2">
      {problems.map((p) => (
        <li key={p}>{p}</li>
      ))}
    </ul>
  </CAlert>
)

PreflightErrorPanel.propTypes = {
  problems: PropTypes.arrayOf(PropTypes.string).isRequired,
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------
const Schedules = () => {
  const [mode, setMode] = useState('full')
  const [activeTaskId, setActiveTaskId] = useState(null)
  const [preflightErrors, setPreflightErrors] = useState([])

  const { data: timeslots, isLoading: loadingTs } = useTimeslots()
  const { data: drafts = [], refetch: refetchDrafts } = useDrafts()

  const generateMutation = useGenerateSchedule()
  const approveMutation = useApproveDraft()
  const rejectMutation = useRejectDraft()

  const { data: taskData } = useScheduleTaskStatus(activeTaskId)

  // Quando tarefa terminal, limpar activeTaskId e refrescar rascunhos
  useEffect(() => {
    const status = taskData?.status ?? ''
    if (activeTaskId && TERMINAL_STATUSES.some(s => status.includes(s))) {
      void refetchDrafts()
    }
  }, [taskData?.status, activeTaskId, refetchDrafts])

  const handleGenerate = async () => {
    setPreflightErrors([])
    setActiveTaskId(null)
    try {
      const result = await generateMutation.mutateAsync(mode)
      if (result?.task_id) setActiveTaskId(result.task_id)
    } catch (err) {
      const problems = err?.response?.data?.detail?.problems
      if (Array.isArray(problems)) {
        setPreflightErrors(problems)
      }
    }
  }

  const isGenerating = isPending(taskData?.status)

  return (
    <div className="p-4">
      {/* Cabeçalho */}
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendar} className="me-2 text-primary" />
            Horários Escolares
          </h2>
          <small className="text-muted">
            Gere e gira horários por CP-SAT. O modo Reparação preserva o máximo do horário atual.
          </small>
        </div>

        {/* Controlos de geração */}
        <CCard className="border-0 shadow-sm">
          <CCardBody className="py-2 px-3">
            <CRow className="g-2 align-items-end">
              <CCol xs="auto">
                <CFormLabel htmlFor="modeSelect" className="small mb-1 text-muted">
                  Modo
                </CFormLabel>
                <CFormSelect
                  id="modeSelect"
                  size="sm"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={isGenerating}
                  style={{ minWidth: '160px' }}
                >
                  <option value="full">Completo (de raiz)</option>
                  <option value="repair">Reparação (mín. alterações)</option>
                </CFormSelect>
              </CCol>
              <CCol xs="auto">
                <CButton
                  color="primary"
                  size="sm"
                  disabled={isGenerating || generateMutation.isPending}
                  onClick={() => { void handleGenerate() }}
                >
                  {isGenerating
                    ? <><CSpinner size="sm" className="me-1" />A gerar…</>
                    : <><CIcon icon={cilReload} className="me-1" />Gerar Horário</>
                  }
                </CButton>
              </CCol>
            </CRow>
          </CCardBody>
        </CCard>
      </div>

      {/* Erros de preflight */}
      {preflightErrors.length > 0 && (
        <PreflightErrorPanel problems={preflightErrors} />
      )}

      {/* Estado da geração em curso */}
      {activeTaskId && (
        <GenerationStatusPanel taskId={activeTaskId} />
      )}

      {/* Rascunhos pendentes */}
      {[...drafts].sort((a, b) => a.generation_id.localeCompare(b.generation_id)).map(draft => (
        <DraftPanel
          key={draft.generation_id}
          draft={draft}
          onApprove={(genId) => approveMutation.mutateAsync(genId)}
          onReject={(genId) => rejectMutation.mutateAsync(genId)}
          isApproving={approveMutation.isPending}
          isRejecting={rejectMutation.isPending}
        />
      ))}

      {/* Grelha de horário atual */}
      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-transparent fw-semibold d-flex align-items-center gap-2">
          Grelha de Períodos Horários
          {drafts.length > 0 && (
            <CBadge color="warning" className="ms-2">
              {drafts.length} rascunho{drafts.length !== 1 ? 's' : ''} pendente{drafts.length !== 1 ? 's' : ''}
            </CBadge>
          )}
        </CCardHeader>
        <CCardBody className="p-0">
          {loadingTs ? (
            <div className="p-5 text-center">
              <CSpinner />
              <div className="mt-2 text-muted">A carregar grelha…</div>
            </div>
          ) : (
            <TimeGrid timeslots={timeslots ?? []} />
          )}
        </CCardBody>
      </CCard>
    </div>
  )
}

export default Schedules
