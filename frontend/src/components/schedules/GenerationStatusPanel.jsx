import { CSpinner } from '@coreui/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useScheduleTaskStatus } from '../../features/scheduling/data'
import FailureState from '../FailureState'
import FeedbackBanner from '../FeedbackBanner'
import { getApiErrorPresentation } from '../../utils/apiErrors'
import { formatDurationMinutes } from '../../utils/formatUtils'

const ACTIVE_STATUSES = new Set(['QUEUED', 'RUNNING', 'VALIDATING'])
const TERMINAL_STATUSES = new Set([
  'CANCELLED', 'FAILED', 'STALE', 'INFEASIBLE', 'INCONCLUSIVE',
])

const STATUS_LABELS = {
  QUEUED: 'Em fila',
  RUNNING: 'A organizar as aulas',
  VALIDATING: 'A validar a proposta',
  SUCCEEDED: 'Proposta pronta para revisão',
  CANCELLED: 'Geração cancelada',
  FAILED: 'Não foi possível concluir a geração',
  STALE: 'Os dados mudaram durante a geração',
  INFEASIBLE: 'Não é possível colocar todas as aulas com estas condições',
  INCONCLUSIVE: 'Não foi possível concluir a pesquisa',
}

const TERMINAL_MESSAGES = {
  CANCELLED: 'A geração foi cancelada. O horário ativo não foi alterado.',
  STALE: 'Os dados da escola mudaram durante a geração. Gere uma nova proposta.',
  INFEASIBLE:
    'Não é possível colocar todas as aulas com estas condições. Reveja disponibilidades, salas, professor atribuído ou datas.',
  INCONCLUSIVE:
    'Não foi possível concluir a pesquisa. Isto não significa que o horário seja impossível.',
  FAILED: 'Ocorreu um erro durante a geração. Tente novamente.',
}

const JOINT_NO_COMMON_TIME = 'JOINT_NO_COMMON_TIME'
const TEACHER_PRESENCE_RULES = 'TEACHER_PRESENCE_RULES'
// T09: the presence estimate is shown only in these no-schedule terminal states.
const PRESENCE_ADVISORY_STATUSES = new Set(['INFEASIBLE', 'FAILED', 'INCONCLUSIVE'])

// The joint message names every member class and the subject only when the read
// model resolved all of them. A deleted class or subject keeps the honest
// generic message instead of inventing a name.
const jointDiagnosisContext = (diagnostics) => {
  const rows = (Array.isArray(diagnostics) ? diagnostics : [])
    .filter((item) => item.code === JOINT_NO_COMMON_TIME)
  if (rows.length === 0) return null
  const subject = rows[0].subject_name
  const classNames = []
  const seen = new Set()
  for (const row of rows) {
    if (!row.class_id || !row.class_name) return null
    if (seen.has(row.class_id)) continue
    seen.add(row.class_id)
    classNames.push(row.class_name)
  }
  if (!subject || classNames.length < 2) return null
  return { classNames: classNames.join(', '), subject }
}

// A proven class diagnostic always carries the current name, the course and a
// positive deficit. An unresolved class (deleted after the failure) or one
// without a proven number never appears as a known name or as "0 min".
const provenClassDiagnostics = (diagnostics) => (Array.isArray(diagnostics) ? diagnostics : [])
  .filter((item) => (
    item.class_id
    && item.class_name
    && item.course_id
    && typeof item.minimum_missing_minutes === 'number'
    && Number.isFinite(item.minimum_missing_minutes)
    && item.minimum_missing_minutes > 0
  ))

const DiagnosticLine = ({ diagnostic }) => {
  const isIntersection = diagnostic.code === 'INSUFFICIENT_INTERSECTION' && diagnostic.subject_name
  return (
    <li>
      <Link to={`/courses/${diagnostic.course_id}/classes/${diagnostic.class_id}`}>
        {diagnostic.class_name}
      </Link>
      {isIntersection ? ` · ${diagnostic.subject_name}` : ''}
      {`: faltam pelo menos ${formatDurationMinutes(Math.ceil(diagnostic.minimum_missing_minutes))}`}
      {isIntersection ? ' em que a turma e o professor estejam livres.' : '.'}
    </li>
  )
}

const GenerationStatusPanel = ({ jobId }) => {
  const { data: job, isLoading, isError, error, refetch } = useScheduleTaskStatus(jobId)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = globalThis.setInterval(() => setNow(Date.now()), 5000)
    return () => globalThis.clearInterval(timer)
  }, [])

  if (isLoading || (!job && !isError)) {
    return (
      <div className="mb-4">
        <FeedbackBanner tone="info">
          <span className="d-inline-flex align-items-center gap-2">
            <CSpinner size="sm" />
            A aguardar...
          </span>
        </FeedbackBanner>
      </div>
    )
  }

  if (isError) {
    const presentation = getApiErrorPresentation(error, 'schedule.load')
    const status = error?.response?.status
    return (
      <FailureState
        presentation={presentation}
        onRetry={status === 403 ? undefined : status === 401 ? undefined : () => void refetch()}
        navigationTo={status === 401 ? '/login' : undefined}
        navigationLabel={status === 401 ? 'Entrar novamente' : undefined}
        variant="inline"
      />
    )
  }
  const status = job.status ?? ''
  const isActive = ACTIVE_STATUSES.has(status)
  if (status === 'SUCCEEDED') {
    return (
      <div className="mb-4">
        <FeedbackBanner tone="success">
          <strong>{STATUS_LABELS.SUCCEEDED}</strong>
        </FeedbackBanner>
      </div>
    )
  }
  if (TERMINAL_STATUSES.has(status)) {
    const isStaleLike = status === 'CANCELLED' || status === 'STALE'
    const jobCodes = [job.result_code, job.stop_reason]
    const roomBlocked = jobCodes.includes('NO_ELIGIBLE_ROOM') || jobCodes.includes('JOINT_ROOM_CAPACITY')
    const protectedConflict = status === 'INFEASIBLE' && job.diagnostics?.some(
      (item) => item.code === 'PROTECTED_AVAILABILITY_CONFLICT',
    )
    const jointDiagnostics = status === 'INFEASIBLE'
      ? (Array.isArray(job.diagnostics) ? job.diagnostics : [])
          .filter((item) => item.code === JOINT_NO_COMMON_TIME)
      : []
    const jointContext = status === 'INFEASIBLE' ? jointDiagnosisContext(job.diagnostics) : null
    const jointNoCommonTime = jobCodes.includes(JOINT_NO_COMMON_TIME)
      || jointDiagnostics.length > 0
    // The presence estimate is an extra advisory rendered alongside the primary
    // diagnosis; it never replaces a proven room, protected, joint or class
    // message, and it appears only in the statuses T09 allows.
    const presenceAdvisory = PRESENCE_ADVISORY_STATUSES.has(status)
      ? (Array.isArray(job.diagnostics) ? job.diagnostics : [])
          .filter((item) => item.code === TEACHER_PRESENCE_RULES)
      : []
    const presenceNames = presenceAdvisory.map((item) => item.teacher_name).filter(Boolean)
    const classDiagnostics = status === 'INFEASIBLE' && !roomBlocked
      ? provenClassDiagnostics(job.diagnostics)
      : []
    return (
      <div className="mb-4" data-testid="generation-terminal">
        <FeedbackBanner tone={isStaleLike ? 'warning' : 'danger'}>
          <strong>{STATUS_LABELS[status] || 'Estado da geração indisponível'}</strong>
          {' '}
          {roomBlocked ? (
            <>
              Existem turmas sem sala compatível com o tipo e a lotação.{' '}
              <Link to="/rooms">Abrir Salas</Link> para corrigir e voltar a gerar.
            </>
          ) : protectedConflict ? (
            <>
              Há aulas protegidas que coincidem com blocos marcados como Impossível.{' '}
              Reveja a disponibilidade ou a janela de proteção antes de voltar a gerar.{' '}
              <Link to="/config">Abrir Configuração</Link>.
            </>
          ) : jointNoCommonTime && !isStaleLike ? (
            <>
              <span>
                {jointContext
                  ? `As turmas ${jointContext.classNames} não têm horas livres em comum para ${jointContext.subject}.`
                  : 'As turmas da aula conjunta não têm horas livres em comum.'}
              </span>{' '}
              Reveja as disponibilidades das turmas e do professor.{' '}
              <Link to="/config">Abrir Configuração</Link>.
            </>
          ) : classDiagnostics.length > 0 ? (
            <>
              Turmas sem tempo suficiente:
              <ul className="mb-1 mt-1 ps-3">
                {classDiagnostics.map((diagnostic) => (
                  <DiagnosticLine key={diagnostic.class_id} diagnostic={diagnostic} />
                ))}
              </ul>
              Reveja a disponibilidade destas turmas.
            </>
          ) : (TERMINAL_MESSAGES[status] || '')}
          {presenceAdvisory.length > 0 && (
            <>
              {' '}
              <span>
                {presenceNames.length > 0
                  ? `Não foi possível cumprir as regras de presença. Professores com mínimo de horas: ${presenceNames.join(', ')}. Experimente baixar o mínimo, aumentar o furo máximo ou alargar a disponibilidade.`
                  : 'Não foi possível cumprir as regras de presença. Experimente baixar o mínimo, aumentar o furo máximo ou alargar a disponibilidade.'}
              </span>{' '}
              <Link to="/members">Abrir Equipa</Link>.
            </>
          )}
        </FeedbackBanner>
      </div>
    )
  }
  if (!isActive) {
    return <FailureState presentation={getApiErrorPresentation({}, 'schedule.generate')} variant="inline" />
  }
  const queuedTooLong = status === 'QUEUED'
    && job.queued_at
    && now - new Date(job.queued_at).getTime() >= 60_000
  return (
    <div className="mb-4">
      <FeedbackBanner tone="info">
        <span className="d-inline-flex align-items-center gap-2">
          {isActive && <CSpinner size="sm" />}
          <strong>{STATUS_LABELS[status]}</strong>
          {status === 'QUEUED' && job.queue_position > 1 && (
            <span className="small">· {job.queue_position}.º pedido em espera</span>
          )}
        </span>
        {queuedTooLong && (
          <>
            <br />
            A aguardar a conclusão de outro pedido. Pode sair desta página com segurança.
          </>
        )}
      </FeedbackBanner>
    </div>
  )
}

export default GenerationStatusPanel
