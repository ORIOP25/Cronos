import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CProgress,
  CProgressBar,
} from '@coreui/react'
import { useTutorialSimulation } from '../tutorial/tutorialHooks'
import { usePrevalidation } from '../readiness/data'
import PageHeader from '../../components/PageHeader'
import StatePanel from '../../components/StatePanel'
import { getApiErrorMessage } from '../../utils/apiErrors'

const BLOCK_LABELS = Object.freeze({
  ACTIVE_CLASSES: 'Turmas ativas',
  MODULES: 'Módulos',
  TEACHER_ASSIGNMENT: 'Atribuição docente',
  CLASS_SUBJECTS: 'Associações turma-disciplina',
  COMPATIBLE_ROOM: 'Salas compatíveis',
  TIMESLOTS: 'Grelha de tempos letivos',
  TEACHER_AVAILABILITY: 'Disponibilidade docente',
})

function statusFor(steps, code) {
  return steps.find((step) => step.code === code)?.status || 'PENDING'
}

function firstPendingRoute(steps, codes) {
  return codes.map((code) => steps.find((step) => step.code === code && step.status !== 'COMPLETE'))
    .find(Boolean)?.route || null
}

export function PreparationDashboard({
  orgId,
  userId,
  organizationName,
  foundationStatus = 'NOT_STARTED',
  bases,
  autoStartGuide = true,
}) {
  const navigate = useNavigate()
  const tutorial = useTutorialSimulation({ orgId, userId })
  const { isHydrated, status } = tutorial
  const fingerprint = bases?.depth === 7 && bases?.complete ? bases.fingerprint : null
  const prevalidation = usePrevalidation({ fingerprint, enabled: Boolean(fingerprint) })

  useEffect(() => {
    if (autoStartGuide && isHydrated && status === 'NOT_STARTED') navigate('/guide', { replace: true })
  }, [autoStartGuide, isHydrated, navigate, status])

  if (!bases || typeof bases !== 'object' || !Array.isArray(bases.steps)) {
    return <StatePanel state="error" title="Resposta de readiness inválida" description="As bases de preparação não foram devolvidas pelo servidor." />
  }

  const percentage = bases.percentage ?? 0
  const depth = bases.depth ?? 0
  const complete = Boolean(bases.complete)
  const steps = bases.steps
  const issues = [
    ...(Array.isArray(bases.issues) ? bases.issues : []),
    ...(Array.isArray(prevalidation.data?.issues) ? prevalidation.data.issues : []),
  ]
  const prevalidationStatus = prevalidation.isError
    ? 'ERROR'
    : prevalidation.isFetching
      ? 'CHECKING'
      : prevalidation.data?.status || (complete ? 'BLOCKED' : 'NOT_READY')
  const canGenerate = ['READY', 'READY_WITH_WARNINGS'].includes(prevalidationStatus)
  const prevalidationErrorMessage = prevalidation.error?.response?.status === 409
    && prevalidation.error?.response?.data?.detail?.code === 'PREFLIGHT_STALE'
    ? 'Os dados da escola foram alterados. Recalcule a prontidão antes de gerar.'
    : getApiErrorMessage(prevalidation.error, 'Não foi possível validar os dados da escola.')

  const blocks = [
    {
      id: 'foundation',
      title: 'Fundação',
      codes: [],
      status: foundationStatus === 'COMPLETED' ? 'COMPLETE' : 'PENDING',
      route: foundationStatus === 'COMPLETED' ? null : '/foundation',
    },
    {
      id: 'offer',
      title: 'Oferta',
      codes: ['ACTIVE_CLASSES', 'MODULES'],
      route: firstPendingRoute(steps, ['ACTIVE_CLASSES', 'MODULES']),
    },
    {
      id: 'people',
      title: 'Pessoas',
      codes: ['TEACHER_ASSIGNMENT'],
      route: firstPendingRoute(steps, ['TEACHER_ASSIGNMENT']) || '/members',
    },
    {
      id: 'associations',
      title: 'Associações',
      codes: ['CLASS_SUBJECTS', 'COMPATIBLE_ROOM'],
      route: firstPendingRoute(steps, ['CLASS_SUBJECTS', 'COMPATIBLE_ROOM']),
    },
    {
      id: 'first-schedule',
      title: 'Primeiro horário',
      codes: ['TIMESLOTS', 'TEACHER_AVAILABILITY'],
      route: firstPendingRoute(steps, ['TIMESLOTS', 'TEACHER_AVAILABILITY']) || '/schedules',
      status: complete
        ? (canGenerate ? 'COMPLETE' : prevalidationStatus)
        : null,
    },
  ].map((block) => ({
    ...block,
    status: block.status || (block.codes.length > 0 && block.codes.every((code) => statusFor(steps, code) === 'COMPLETE') ? 'COMPLETE' : 'PENDING'),
  }))

  return (
    <div className="preparation-dashboard" data-testid="preparation-dashboard">
      <PageHeader
        preTitle="Fase de Preparação"
        title="Prontidão das Bases Escolares"
        context={`Escola: ${organizationName || 'a sua escola'}`}
        description="Complete os cinco blocos antes de lançar a geração do primeiro horário."
      />

      <CCard className="mb-4 shadow-sm border-0 bg-primary text-white">
        <CCardBody className="p-4">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <CBadge color="light" textColor="primary" className="fw-bold text-uppercase mb-2">
                Nível de prontidão: {depth}/7
              </CBadge>
              <h3 className="h4 fw-bold mb-1">
                {complete ? 'Todas as bases estão prontas para geração.' : `Prontidão das bases: ${percentage}%`}
              </h3>
              <p className="mb-0 text-white-50 small">A geração usa os dados atualmente registados na escola.</p>
            </div>
            <div className="d-flex gap-2">
              <CButton
                color="light"
                variant="outline"
                className="text-white border-white"
                onClick={() => {
                  if (tutorial.status !== 'IN_PROGRESS') tutorial.repeatTutorial()
                  navigate('/guide')
                }}
              >
                {tutorial.status === 'IN_PROGRESS' ? 'Retomar guia' : 'Repetir guia'}
              </CButton>
              <CButton
                color="light"
                className="text-primary fw-bold px-4"
                disabled={!canGenerate}
                onClick={() => navigate('/schedules')}
              >
                {prevalidationStatus === 'CHECKING' ? 'A validar…' : 'Gerar primeiro horário →'}
              </CButton>
            </div>
          </div>
          <CProgress height={8} className="bg-white bg-opacity-25 mt-2">
            <CProgressBar value={percentage} color="warning" />
          </CProgress>
        </CCardBody>
      </CCard>

      <div className="preparation-blocks d-grid gap-3" data-testid="preparation-blocks">
        {blocks.map((block, index) => {
          const pendingCode = block.codes.find((code) => statusFor(steps, code) !== 'COMPLETE')
          const blockerRoute = issues.find((issue) => issue.severity === 'BLOCKER')?.route
          const actionRoute = block.id === 'first-schedule' && blockerRoute ? blockerRoute : block.route
          const needsPrevalidationCorrection = block.id === 'first-schedule'
            && complete
            && !canGenerate
          const showPrevalidationRetry = block.id === 'first-schedule' && prevalidation.isError
          const showRouteAction = actionRoute
            && !showPrevalidationRetry
            && prevalidationStatus !== 'CHECKING'
            && (block.status !== 'COMPLETE' || needsPrevalidationCorrection)
          return (
            <CCard key={block.id} data-testid={`preparation-block-${block.id}`} className="shadow-sm border-0">
              <CCardBody className="d-flex justify-content-between align-items-start gap-3">
                <div>
                  <p className="text-uppercase text-muted small mb-1">Bloco {index + 1}</p>
                  <h3 className="h5 fw-bold mb-2">{block.title}</h3>
                  <p className="text-muted mb-2">
                    {block.status === 'COMPLETE'
                      ? 'Concluído.'
                      : block.id === 'first-schedule' && prevalidation.isError
                        ? 'Não foi possível validar as bases.'
                      : pendingCode
                        ? `Pendente: ${BLOCK_LABELS[pendingCode] || pendingCode}.`
                        : block.id === 'first-schedule'
                          ? `Prevalidation: ${prevalidationStatus}.`
                          : 'Configure este bloco para continuar.'}
                  </p>
                  {block.id === 'first-schedule' && <p className="small text-muted mb-0">Prevalidation: {prevalidationStatus}.</p>}
                  {showPrevalidationRetry && (
                    <div className="small text-danger mt-2" role="alert">
                      <span>{prevalidationErrorMessage}</span>{' '}
                      <CButton
                        color="link"
                        size="sm"
                        className="p-0 align-baseline"
                        onClick={() => void prevalidation.refetch()}
                        disabled={prevalidation.isFetching}
                      >
                        Tentar novamente
                      </CButton>
                    </div>
                  )}
                </div>
                {showRouteAction && (
                  <CButton color="primary" size="sm" onClick={() => navigate(actionRoute)}>
                    {block.id === 'first-schedule' && canGenerate ? 'Abrir geração' : 'Corrigir bloco'}
                  </CButton>
                )}
              </CCardBody>
            </CCard>
          )
        })}
      </div>

      {issues.length > 0 && (
        <CCard className="shadow-sm border-0 mt-4" data-testid="preparation-issues">
          <CCardBody>
            <h3 className="h5 fw-bold">Issues de preparação</h3>
            <ul className="mb-0">
              {issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}><strong>{issue.code}</strong> · {issue.severity} · {issue.message} · {issue.route}</li>
              ))}
            </ul>
          </CCardBody>
        </CCard>
      )}
    </div>
  )
}
