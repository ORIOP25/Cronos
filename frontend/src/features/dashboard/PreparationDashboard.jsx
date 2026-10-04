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

const STEP_LABELS = Object.freeze({
  ACTIVE_CLASSES: 'Pelo menos uma turma ativa registada',
  MODULES: 'Disciplinas com módulos UFCD e carga horária definida',
  TEACHERS: 'Pelo menos um professor ativo registado',
  TEACHER_ASSIGNMENT: 'Professor competente atribuído à disciplina da turma',
  COMPATIBLE_ROOM: 'Salas compatíveis com tipologia e lotação da turma',
  TEACHER_AVAILABILITY: 'Disponibilidade docente compatível',
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
  const validation = prevalidation || { status: 'BLOCKED' }

  if (!bases || typeof bases !== 'object' || !Array.isArray(bases.steps)) {
    return <StatePanel state="error" title="Não foi possível avaliar a preparação" description="Tente novamente dentro de instantes." />
  }

  const percentage = bases.percentage ?? 0
  const depth = bases.depth ?? 0
  const complete = Boolean(bases.complete)
  const steps = bases.steps
  const stepCount = steps.length
  const prevalidationStatus = validation.status || 'NOT_READY'
  const canGenerate = complete && ['READY', 'READY_WITH_WARNINGS'].includes(prevalidationStatus)

  const isBlockedByPrevalidation = complete && !canGenerate

  let cardTitle = `Preparação da escola: ${percentage}%`
  let cardDescription = 'Complete o próximo passo pendente na lista abaixo para avançar.'
  if (canGenerate) {
    cardTitle = 'A escola está pronta para gerar o horário.'
    cardDescription = 'A escola reúne as condições necessárias para gerar o horário.'
  } else if (isBlockedByPrevalidation) {
    cardTitle = 'Ainda faltam condições para gerar o horário.'
    cardDescription = (
      <>
        Consulte os bloqueios em{' '}
        <Link to="/schedules" className="text-white fw-semibold">Horários</Link>
        {' '}antes de gerar.
      </>
    )
  }

  return (
    <div className="preparation-dashboard p-4" data-testid="preparation-dashboard">
      <PageHeader
        preTitle="Fase de Preparação"
        title="Preparação da Escola"
        context={organizationName || 'a sua escola'}
        description={`Complete os ${stepCount} passos de preparação antes de gerar o horário.`}
      />

      <CCard className="mb-4 shadow-sm border-0 bg-primary text-white">
        <CCardBody className="p-4">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <CBadge
                color="light"
                textColor="primary"
                className="fw-bold mb-2"
                aria-label={`Progresso: ${depth} de ${stepCount}`}
              >
                {depth}/{stepCount}
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

      <CCard className="shadow-sm border-0 mb-4">
        <CCardBody className="p-4">
          <h2 className="h5 fw-bold mb-3 text-dark">Passos de preparação</h2>
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
                      <h3 className="h6 mb-0 fw-semibold text-dark">{index + 1}. {STEP_LABELS[step.code] || 'Passo de preparação'}</h3>
                      <small className="text-muted">
                        {isPassed
                          ? 'Concluído'
                          : isCurrentTarget
                            ? 'Complete este passo para avançar'
                            : 'Conclua primeiro o passo anterior'}
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
