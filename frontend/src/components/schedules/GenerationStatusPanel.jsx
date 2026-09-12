import { CAlert, CSpinner } from '@coreui/react'
import { useEffect, useState } from 'react'
import { useScheduleTaskStatus } from '../../features/scheduling/data'
import FailureState from '../FailureState'
import { getApiErrorPresentation } from '../../utils/apiErrors'

const STATUS_LABELS = {
  QUEUED: 'Geração em fila',
  RUNNING: 'A gerar horário',
  CANCEL_REQUESTED: 'A cancelar geração',
  CANCELED: 'Geração cancelada',
  SUCCEEDED: 'Rascunho pronto para revisão',
  NO_VALID_OUTPUT: 'Não foi possível gerar um horário válido',
  FAILED: 'Erro na geração',
}

const TERMINAL_STATUSES = new Set(['CANCELED', 'FAILED', 'NO_VALID_OUTPUT'])
const ACTIVE_STATUSES = new Set(['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'])

function alertColor(status) {
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'CANCELED' || status === 'CANCEL_REQUESTED') return 'warning'
  if (status === 'FAILED' || status === 'NO_VALID_OUTPUT') return 'danger'
  return 'info'
}

const GenerationStatusPanel = ({ jobId }) => {
  const { data: job } = useScheduleTaskStatus(jobId)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = globalThis.setInterval(() => setNow(Date.now()), 5000)
    return () => globalThis.clearInterval(timer)
  }, [])

  if (!job) {
    return (
      <CAlert color="info" className="d-flex align-items-center gap-2 mb-4">
        <CSpinner size="sm" />
        A aguardar resposta do servidor...
      </CAlert>
    )
  }

  const status = job.job_status ?? ''
  const isRunning = ACTIVE_STATUSES.has(status)
  if (TERMINAL_STATUSES.has(status)) {
    const failureCode = job.failure_code || (status === 'CANCELED' ? 'CANCELED' : status)
    const presentation = getApiErrorPresentation({
      response: { data: { detail: { code: failureCode, reference: job.failure_reference } } },
    }, 'schedule.generate')
    return <FailureState presentation={presentation} variant="inline" />
  }
  if (!ACTIVE_STATUSES.has(status)) {
    return <FailureState presentation={getApiErrorPresentation({}, 'schedule.generate')} variant="inline" />
  }
  const queuedTooLong = status === 'QUEUED'
    && job.queued_at
    && now - new Date(job.queued_at).getTime() >= 60_000
  return (
    <CAlert color={alertColor(status)} className="mb-4">
      <div className="d-flex align-items-center gap-2">
        {isRunning && <CSpinner size="sm" />}
        <strong>{STATUS_LABELS[status]}</strong>
      </div>
      {queuedTooLong && <div className="small mt-2">A geração está a aguardar execução. Pode sair desta página com segurança.</div>}
    </CAlert>
  )
}

export default GenerationStatusPanel
