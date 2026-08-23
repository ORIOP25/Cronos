import { useEffect } from 'react'
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
import { TutorialModal } from '../tutorial/TutorialModal'
import PageHeader from '../../components/PageHeader'

export function PreparationDashboard({ orgId, userId, organizationName, bases }) {
  const navigate = useNavigate()
  const tutorial = useTutorialSimulation({ orgId, userId })
  const { isHydrated, isOpen, status, openTutorial } = tutorial

  useEffect(() => {
    if (isHydrated && !isOpen && status === 'NOT_STARTED') {
      openTutorial()
    }
  }, [isHydrated, isOpen, status, openTutorial])

  const percentage = bases?.percentage ?? 0
  const depth = bases?.depth ?? 0
  const complete = Boolean(bases?.complete)

  const steps = bases?.steps || [
    { code: 'ACTIVE_CLASSES', status: 'PENDING', route: '/courses' },
    { code: 'CLASS_SUBJECTS', status: 'PENDING', route: '/classes' },
    { code: 'MODULES', status: 'PENDING', route: '/subjects' },
    { code: 'TEACHER_ASSIGNMENT', status: 'PENDING', route: '/members' },
    { code: 'COMPATIBLE_ROOM', status: 'PENDING', route: '/rooms' },
    { code: 'TIMESLOTS', status: 'PENDING', route: '/config' },
    { code: 'TEACHER_AVAILABILITY', status: 'PENDING', route: '/members' },
  ]

  const stepLabels = {
    ACTIVE_CLASSES: '1. Pelo menos uma Turma ativa registada',
    CLASS_SUBJECTS: '2. Associação Turma-Disciplina com ano curricular válido',
    MODULES: '3. Disciplinas com Módulos UFCD e carga horária definida',
    TEACHER_ASSIGNMENT: '4. Docentes com qualificação e competência atribuídos',
    COMPATIBLE_ROOM: '5. Salas compatíveis com tipologia e lotação da turma',
    TIMESLOTS: '6. Grelha semanal de tempos letivos configurada',
    TEACHER_AVAILABILITY: '7. Disponibilidade docente compatível (não impossível)',
  }

  return (
    <div className="preparation-dashboard" data-testid="preparation-dashboard">
      <PageHeader
        preTitle="Fase de Preparação"
        title="Prontidão das Bases Escolares"
        context={`Escola: ${organizationName}`}
        description="Complete a cadeia cumulativa de 7 níveis antes de lançar a geração de horários."
      />

      {/* Banner Principal de Prontidão */}
      <CCard className="mb-4 shadow-sm border-0 bg-primary text-white">
        <CCardBody className="p-4">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <CBadge color="light" textColor="primary" className="fw-bold text-uppercase mb-2">
                Nível de Prontidão: {depth}/7
              </CBadge>
              <h3 className="h4 fw-bold mb-1">
                {complete ? '🎉 Todas as bases estão prontas para geração!' : `Prontidão das Bases: ${percentage}% (${depth}/7 níveis atingidos)`}
              </h3>
              <p className="mb-0 text-white-50 small">
                {complete
                  ? 'A escola cumpre todos os invariantes do motor CP-SAT do Google OR-Tools.'
                  : 'Complete o próximo nível pendente na lista abaixo para progredir.'}
              </p>
            </div>
            <div className="d-flex gap-2">
              <CButton
                color="light"
                variant="outline"
                className="text-white border-white"
                onClick={tutorial.status === 'IN_PROGRESS' ? tutorial.openTutorial : tutorial.repeatTutorial}
              >
                {tutorial.status === 'IN_PROGRESS' ? 'Retomar guia' : 'Repetir guia'} 🎓
              </CButton>
              <CButton
                color="light"
                className="text-primary fw-bold px-4"
                disabled={!complete}
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

      {/* Lista Cumulativa de Níveis */}
      <CCard className="shadow-sm border-0 mb-4">
        <CCardBody className="p-4">
          <h4 className="h5 fw-bold mb-3 text-dark">Cadeia Cumulativa de Validação</h4>
          <div className="d-flex flex-column gap-3">
            {steps.map((st, idx) => {
              const isPassed = st.status === 'COMPLETE'
              const isCurrentTarget = !isPassed && (idx === 0 || steps[idx - 1].status === 'COMPLETE')

              return (
                <div
                  key={st.code}
                  className={`p-3 rounded border d-flex justify-content-between align-items-center ${
                    isPassed
                      ? 'bg-light border-success-subtle'
                      : isCurrentTarget
                        ? 'bg-white border-primary shadow-sm'
                        : 'bg-light text-muted opacity-75'
                  }`}
                >
                  <div className="d-flex align-items-center gap-3">
                    <span
                      className={`badge rounded-pill ${
                        isPassed ? 'bg-success' : isCurrentTarget ? 'bg-primary' : 'bg-secondary'
                      }`}
                    >
                      {isPassed ? '✓ Concluído' : isCurrentTarget ? 'A Realizar' : 'Bloqueado'}
                    </span>
                    <div>
                      <h6 className="mb-0 fw-semibold text-dark">
                        {stepLabels[st.code] || st.code}
                      </h6>
                      <small className="text-muted">
                        {isPassed
                          ? 'Invariante satisfeito'
                          : isCurrentTarget
                            ? 'Configure este recurso para desbloquear o próximo nível'
                            : 'Requer que o nível anterior esteja concluído'}
                      </small>
                    </div>
                  </div>

                  <div>
                    {isCurrentTarget && (
                      <Link to={st.route} className="btn btn-sm btn-primary">
                        Configurar →
                      </Link>
                    )}
                    {isPassed && (
                      <Link to={st.route} className="btn btn-sm btn-outline-secondary">
                        Ver
                      </Link>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </CCardBody>
      </CCard>

      {/* Tutorial Modal */}
      <TutorialModal
        isOpen={tutorial.isOpen}
        currentStep={tutorial.currentStep}
        currentStepIndex={tutorial.currentStepIndex}
        totalSteps={tutorial.totalSteps}
        progressPercent={tutorial.progressPercent}
        completed={tutorial.completed}
        simulationData={tutorial.simulationData}
        onNext={tutorial.nextStep}
        onPrev={tutorial.prevStep}
        onSkip={tutorial.skipStep}
        onSkipTutorial={tutorial.skipTutorial}
        onClose={tutorial.exitTutorial}
      />
    </div>
  )
}
