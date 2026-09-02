import { useEffect, useMemo, useRef, useState } from 'react'
import { TUTORIAL_STEPS } from './tutorialContent'
import { createTutorialScenario } from './tutorialScenario'
import { TutorialInstructionPanel } from './TutorialInstructionPanel'
import { TutorialShell } from './TutorialShell'
import { TutorialApiBoundary } from './TutorialApiBoundary'
import { TutorialLivePage } from './TutorialLivePage'
import { TutorialInteractionGuard } from './TutorialInteractionGuard'

export function TutorialWorkspace({ tutorial, onExit, onSkipTutorial }) {
  const [reviewStepIndex, setReviewStepIndex] = useState(null)
  const instructionRef = useRef(null)
  const reviewMode = Number.isInteger(reviewStepIndex)
  const screenStep = reviewMode ? TUTORIAL_STEPS[reviewStepIndex] : tutorial.currentStep
  const screenScenario = useMemo(() => createTutorialScenario(screenStep.id), [screenStep.id])
  const presentationKey = `${tutorial.storageKey ?? ''}:${tutorial.tutorialRunId ?? 'unstarted'}:${screenStep.id}:${reviewMode ? 'review' : 'current'}`

  useEffect(() => {
    const focusTimer = globalThis.setTimeout(() => instructionRef.current?.focus(), 0)
    return () => globalThis.clearTimeout(focusTimer)
  }, [tutorial.stepId])

  useEffect(() => {
    if (!reviewMode) return undefined
    const focusTimer = globalThis.setTimeout(() => instructionRef.current?.focus(), 0)
    return () => globalThis.clearTimeout(focusTimer)
  }, [reviewMode, reviewStepIndex])

  const beginReview = () => {
    if (tutorial.currentStepIndex > 0) setReviewStepIndex(tutorial.currentStepIndex - 1)
  }

  const reviewPrevious = () => {
    setReviewStepIndex((index) => (index > 0 ? index - 1 : index))
  }

  const panel = (
    <TutorialInstructionPanel
      ref={instructionRef}
      step={screenStep}
      stepIndex={tutorial.currentStepIndex}
      totalSteps={tutorial.totalSteps}
      progressPercent={tutorial.progressPercent}
      reviewMode={reviewMode}
      reviewStepIndex={reviewStepIndex}
      onPrevious={reviewMode ? reviewPrevious : beginReview}
      onReturnToCurrent={() => setReviewStepIndex(null)}
      onExit={onExit}
      onSkipTutorial={onSkipTutorial}
      onAdvance={() => tutorial.advanceTutorial(screenStep.id)}
      persistenceError={tutorial.persistenceError}
    />
  )

  return (
    <TutorialApiBoundary
      key={presentationKey}
      stepId={screenStep.id}
      readOnly={reviewMode}
      scenario={screenScenario}
    >
      <TutorialShell activeNavItem={screenStep.activeNavItem} panel={panel}>
        <TutorialInteractionGuard step={screenStep} reviewMode={reviewMode} />
        {reviewMode && <div className="tutorial-review-banner" role="status">Está a rever um passo concluído. Volte ao passo atual para continuar.</div>}
        <div className={reviewMode ? 'tutorial-live-page is-reviewing' : 'tutorial-live-page'}>
          <TutorialLivePage
            step={screenStep}
            readOnly={reviewMode}
            allowedActions={reviewMode ? [] : screenStep.allowedActions}
            navigationDisabled
            referenceDate={screenScenario.referenceDate}
          />
        </div>
      </TutorialShell>
    </TutorialApiBoundary>
  )
}
