import { Link, useNavigate } from 'react-router-dom'
import {
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CProgress,
  CProgressBar,
} from '@coreui/react'
import { useTutorialSimulation } from '../tutorial/tutorialHooks'
import PageHeader from '../../components/PageHeader'
import StatePanel from '../../components/StatePanel'
import FeedbackBanner from '../../components/FeedbackBanner'

const STEP_LABELS = Object.freeze({
  ACTIVE_CLASSES: '1. Pelo menos uma Turma ativa registada',
  MODULES: '2. Disciplinas com Módulos UFCD e carga horária definida',
  CLASS_SUBJECTS: '3. Associação Turma-Disciplina com ano curricular válido',
  TEACHER_ASSIGNMENT: '4. Professor competente atribuído à disciplina da turma',
  COMPATIBLE_ROOM: '5. Salas compatíveis com tipologia e lotação da turma',
  TIMESLOTS: '6. Grelha semanal de tempos letivos configurada',
  TEACHER_AVAILABILITY: '7. Disponibilidade docente compatível (não impossível)',
})

export function PreparationDashboard({
  orgId,
  userId,
  organizationName,
  bases,
  prevalidation,
}) {
  const navigate = useNavigate()
  const tutorial = useTutorialSimulation({ orgId, userId })
  const validation = prevalidation || { status: 'BLOCKED', issues: [] }

  if (!bases || typeof bases !== 'object' || !Array.isArray(bases.steps)) {
    return <StatePanel state="error" title="Resposta de readiness inválida" description="As bases de preparação não foram devolvidas pelo servidor." />
  }

  const percentage = bases.percentage ?? 0
  const depth = bases.depth ?? 0
  const complete = Boolean(bases.complete)
  const steps = bases.steps
  const issues = Array.isArray(validation.issues) ? validation.issues : []
  const blockers = issues.filter((i) => i.severity === 'BLOCKER')
  const warnings = issues.filter((i) => i.severity === 'WARNING')
  const prevalidationStatus = validation.status || (complete ? (blockers.length ? 'BLOCKED' : 'READY') : 'NOT_READY')
  const canGenerate = complete && ['READY', 'READY_WITH_WARNINGS'].includes(prevalidationStatus)

  const isReadyWithWarnings = canGenerate && prevalidationStatus === 'READY_WITH_WARNINGS'
  const isReady = canGenerate && prevalidationStatus === 'READY'
  const isBlockedByPrevalidation = complete && !canGenerate

  const cardTitle = isReady
    ? 'Todas as bases estão prontas para geração.'
    : isReadyWithWarnings
      ? 'Bases completas com avisos de validação.'
      : isBlockedByPrevalidation
        ? 'Geração bloqueada por validações adicionais.'
        : `Prontidão das Bases: ${percentage}%`

  const cardDescription = isReady
    ? 'A escola cumpre todos os invariantes do motor de geração.'
    : isReadyWithWarnings
      ? 'A escola cumpre os invariantes base, mas existem avisos a rever.'
      : isBlockedByPrevalidation
        ? 'Resolva os impedimentos identificados abaixo para desbloquear a geração.'
        : 'Complete o próximo nível pendente na lista abaixo para progredir.'

  return (
    <div className="preparation-dashboard p-4" data-testid="preparation-dashboard">
      <PageHeader
        preTitle="Fase de Preparação"
        title="Prontidão das Bases Escolares"
        context={organizationName || 'a sua escola'}
        description="Complete a cadeia cumulativa de 7 níveis antes de lançar a geração de horários."
      />

      <CCard className="mb-4 shadow-sm border-0 bg-primary text-white">
        <CCardBody className="p-4">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <CBadge
                color="light"
                textColor="primary"
                className="fw-bold mb-2"
                aria-label={`Prontidão: ${depth} de 7`}
              >
                {depth}/7
              </CBadge>
              <h3 className="h4 fw-bold mb-1">
                {cardTitle}
              </h3>
              <p className="mb-0 text-white-50 small">
                {cardDescription}
              </p>
            </div>
            <div className="d-flex gap-2">
              <CButton
                color="light"
                variant="outline"
                className="preparation-dashboard__guide-button"
                onClick={() => {
                  const entry = tutorial.status === 'NOT_STARTED' ? 'start' : tutorial.status === 'IN_PROGRESS' ? 'resume' : 'repeat'
                  navigate(`/guide?entry=${entry}`)
                }}
              >
                {tutorial.status === 'NOT_STARTED' ? 'Conhecer o guia' : tutorial.status === 'IN_PROGRESS' ? 'Retomar guia' : 'Repetir guia'}
              </CButton>
              <CButton
                color="light"
                className="text-primary fw-bold px-4"
                disabled={!canGenerate}
                onClick={() => navigate('/schedules')}
              >
                Gerar Horário →
              </CButton>
            </div>
          </div>
          <CProgress height={8} className="bg-white bg-opacity-25 mt-2">
            <CProgressBar value={percentage} color="warning" />
          </CProgress>
        </CCardBody>
      </CCard>

      {issues.length > 0 && (
        <div className="d-flex flex-column gap-3 mb-4" data-testid="preparation-issues">
          {blockers.map((issue) => (
            <FeedbackBanner
              key={`${issue.code}-${issue.route || ''}`}
              tone="danger"
              title={issue.code}
              action={issue.route ? (
                <Link to={issue.route} className="btn btn-sm btn-outline-danger">
                  Resolver →
                </Link>
              ) : null}
            >
              {issue.message}
            </FeedbackBanner>
          ))}
          {warnings.map((issue) => (
            <FeedbackBanner
              key={`${issue.code}-${issue.route || ''}`}
              tone="warning"
              title={issue.code}
              action={issue.route ? (
                <Link to={issue.route} className="btn btn-sm btn-outline-warning">
                  Verificar →
                </Link>
              ) : null}
            >
              {issue.message}
            </FeedbackBanner>
          ))}
        </div>
      )}

      <CCard className="shadow-sm border-0 mb-4">
        <CCardBody className="p-4">
          <h2 className="h5 fw-bold mb-3 text-dark">Cadeia Cumulativa de Validação</h2>
          <div className="d-flex flex-column gap-3" data-testid="preparation-levels">
            {steps.map((step, index) => {
              const isPassed = step.status === 'COMPLETE'
              const isCurrentTarget = !isPassed && (index === 0 || steps[index - 1].status === 'COMPLETE')

              return (
                <div
                  key={step.code}
                  data-testid={`preparation-level-${step.code}`}
                  className={`p-3 rounded border d-flex justify-content-between align-items-center gap-3 ${
                    isPassed
                      ? 'bg-light border-success-subtle'
                      : isCurrentTarget
                        ? 'bg-white border-primary shadow-sm'
                        : 'bg-light text-muted opacity-75'
                  }`}
                >
                  <div className="d-flex align-items-center gap-3">
                    <span className={`badge rounded-pill ${isPassed ? 'bg-success' : isCurrentTarget ? 'bg-primary' : 'bg-secondary'}`}>
                      {isPassed ? '✓ Concluído' : isCurrentTarget ? 'A Realizar' : 'Bloqueado'}
                    </span>
                    <div>
                      <h3 className="h6 mb-0 fw-semibold text-dark">{STEP_LABELS[step.code] || step.code}</h3>
                      <small className="text-muted">
                        {isPassed
                          ? 'Invariante satisfeito'
                          : isCurrentTarget
                            ? 'Configure este recurso para desbloquear o próximo nível'
                            : 'Requer que o nível anterior esteja concluído'}
                      </small>
                    </div>
                  </div>
                  {isCurrentTarget && <Link to={step.route} className="btn btn-sm btn-primary">Configurar →</Link>}
                  {isPassed && <Link to={step.route} className="btn btn-sm btn-outline-secondary">Ver</Link>}
                </div>
              )
            })}
          </div>
        </CCardBody>
      </CCard>

    </div>
  )
}
