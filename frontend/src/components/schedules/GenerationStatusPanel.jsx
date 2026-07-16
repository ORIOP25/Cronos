import { CAlert, CSpinner } from '@coreui/react'
import { useScheduleTaskStatus } from '../../features/scheduling/data'

const STATUS_LABELS = {
  QUEUED: 'Geração em fila',
  RUNNING: 'A gerar horário',
  CANCEL_REQUESTED: 'A cancelar geração',
  CANCELED: 'Geração cancelada',
  SUCCEEDED: 'Rascunho pronto para revisão',
  NO_VALID_OUTPUT: 'Não foi possível gerar um horário válido',
  FAILED: 'Erro na geração',
}

function alertColor(status) {
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'CANCELED' || status === 'CANCEL_REQUESTED') return 'warning'
  if (status === 'FAILED' || status === 'NO_VALID_OUTPUT') return 'danger'
  return 'info'
}

const GenerationStatusPanel = ({ jobId }) => {
  const { data: job } = useScheduleTaskStatus(jobId)

  if (!job) {
    return (
      <CAlert color="info" className="d-flex align-items-center gap-2 mb-4">
        <CSpinner size="sm" />
        A aguardar resposta do servidor...
      </CAlert>
    )
  }

  const status = job.job_status ?? ''
  const isRunning = ['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(status)
  return (
    <CAlert color={alertColor(status)} className="mb-4">
      <div className="d-flex align-items-center gap-2">
        {isRunning && <CSpinner size="sm" />}
        <strong>{STATUS_LABELS[status] ?? status}</strong>
      </div>
      {job.failure_message && <div className="small mt-2">{job.failure_message}</div>}
    </CAlert>
  )
}

export default GenerationStatusPanel
