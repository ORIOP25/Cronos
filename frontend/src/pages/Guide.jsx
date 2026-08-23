import { useEffect } from 'react'
import { useOrganization, useUser } from '@clerk/react'
import { CButton } from '@coreui/react'
import { useTutorialSimulation } from '../features/tutorial/tutorialHooks'
import { TutorialModal } from '../features/tutorial/TutorialModal'

export default function Guide() {
  const { organization } = useOrganization()
  const { user } = useUser()
  const {
    isOpen,
    isHydrated,
    status,
    openTutorial,
    currentStep,
    currentStepIndex,
    totalSteps,
    progressPercent,
    completed,
    simulationData,
    nextStep,
    prevStep,
    skipStep,
    skipTutorial,
    exitTutorial,
    repeatTutorial,
  } = useTutorialSimulation({ orgId: organization?.id, userId: user?.id })

  useEffect(() => {
    if (isHydrated && !isOpen && status !== 'COMPLETED' && status !== 'SKIPPED') {
      openTutorial()
    }
  }, [isHydrated, isOpen, status, openTutorial])

  if (!isOpen) {
    return (
      <div className="container py-5" data-testid="guide-landing">
        <h1 className="h3">Tutorial Interativo</h1>
        <p className="text-muted">O tutorial está guardado para esta organização e utilizador.</p>
        <CButton color="primary" onClick={status === 'IN_PROGRESS' ? openTutorial : repeatTutorial}>
          {status === 'IN_PROGRESS' ? 'Retomar guia' : 'Repetir guia'}
        </CButton>
      </div>
    )
  }

  return (
    <TutorialModal
      isOpen={isOpen}
      currentStep={currentStep}
      currentStepIndex={currentStepIndex}
      totalSteps={totalSteps}
      progressPercent={progressPercent}
      completed={completed}
      simulationData={simulationData}
      onNext={nextStep}
      onPrev={prevStep}
      onSkip={skipStep}
      onSkipTutorial={skipTutorial}
      onClose={exitTutorial}
    />
  )
}
