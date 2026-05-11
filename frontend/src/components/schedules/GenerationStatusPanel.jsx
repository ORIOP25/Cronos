import PropTypes from 'prop-types'
import { CAlert, CSpinner, CProgress } from '@coreui/react'
import { useScheduleTaskStatus } from '../../hooks/useSchoolData'
import { humanizeOperationalDetail } from '../../utils/terminology'

export const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible', 'REVOKED', 'CANCELED']

export function isPending(status) {
  return !!status && !TERMINAL_STATUSES.some(s => status.includes(s))
}

const GENERATION_STATUS_LABELS = {
  PENDING:   'A preparar cálculo do horário…',
  FETCHING:  'A ler dados da escola…',
  SOLVING:   'A calcular o melhor horário para a escola…',
  EXPANDING: 'A expandir para datas reais…',
  SAVING:    'A guardar solução…',
  REVOKED:   'Cancelado.',
  CANCELED:  'Cancelado.',
  SUCCESS:   'Concluído!',
  FAILURE:   'Erro na geração.',
}

const STEP_BY_STATUS = {
  PENDING: 1,
  FETCHING: 2,
  SOLVING: 6,
  EXPANDING: 7,
  SAVING: 9,
  SUCCESS: 10,
}
const DEFAULT_TOTAL_STEPS = 10

function resolveAlertColor(status) {
  if (status.includes('SUCCESS') || status.includes('Success')) return 'success'
  if (status.includes('REVOKED') || status.includes('CANCELED')) return 'warning'
  if (status.includes('FAILURE') || status.includes('Error') || status.includes('Impossible')) return 'danger'
  return 'info'
}

function resolveBusinessStatus(taskData) {
  const resultStatus = taskData?.result?.status
  if (resultStatus === 'Canceled') return 'warning'
  if (resultStatus === 'Error' || resultStatus === 'Impossible') return 'danger'
  if (resultStatus === 'Success') return 'success'
  return null
}

function resolveProgress(taskData) {
  const serverProgress = taskData?.progress ?? taskData?.result?.progress
  if (serverProgress?.current && serverProgress?.total) {
    return {
      current: serverProgress.current,
      total: serverProgress.total,
    }
  }

  const status = taskData?.status ?? ''
  const fallbackCurrent = STEP_BY_STATUS[status]
  if (fallbackCurrent) {
    return {
      current: fallbackCurrent,
      total: DEFAULT_TOTAL_STEPS,
    }
  }
  return null
}

const GenerationStatusPanel = ({ taskId }) => {
  const { data: taskData } = useScheduleTaskStatus(taskId)

  if (!taskData) {
    return (
      <CAlert color="info" className="d-flex align-items-center gap-2 mb-4">
        <CSpinner size="sm" />
        A aguardar resposta do servidor…
      </CAlert>
    )
  }

  const status     = taskData.status ?? ''
  const isRunning  = isPending(status)
  const businessColor = resolveBusinessStatus(taskData)
  const alertColor = businessColor ?? resolveAlertColor(status)
  const label = taskData?.result?.status ?? GENERATION_STATUS_LABELS[status] ?? status
  const rawDetail = taskData?.detail ?? taskData?.result?.detail
  const detail = humanizeOperationalDetail(rawDetail)
  const progress = resolveProgress(taskData)
  const progressValue = progress
    ? (progress.current / progress.total) * 100
    : 0
  const result     = taskData.result

  const isSolving = status === 'SOLVING'

  return (
    <CAlert color={alertColor} className="mb-4">
      <div className="d-flex align-items-center gap-2 mb-2">
        {isRunning && <CSpinner size="sm" />}
        <strong>{label}</strong>
      </div>
      {isSolving && (
        <div className="small text-muted mb-1">Pode demorar alguns minutos.</div>
      )}
      {progress && (
        <div className="small mb-1">
          Etapa {progress.current}/{progress.total}
        </div>
      )}
      {isRunning && (
        <CProgress
          animated
          value={progressValue}
          className="mb-2"
          style={{ height: '6px' }}
        />
      )}
      {detail && (
        <div className="small mt-1">{detail}</div>
      )}
      {result?.is_draft && (
        <div className="small mt-1">
          Rascunho criado com{' '}<strong>{result.count}</strong>{' '}blocos.
          Reveja o diff acima e aprove ou rejeite.
        </div>
      )}
      {result?.mode === 'full' && result?.count && (
        <div className="small mt-1">
          Horário ativo atualizado com{' '}<strong>{result.count}</strong>{' '}blocos.
        </div>
      )}
      {result?.message && (
        <div className="small mt-1">{result.message}</div>
      )}
    </CAlert>
  )
}

GenerationStatusPanel.propTypes = {
  taskId: PropTypes.string.isRequired,
}

export default GenerationStatusPanel
