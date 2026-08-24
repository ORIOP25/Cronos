import { useEffect, useRef, useState } from 'react'
import { TUTORIAL_STEPS, matchTutorialMutation, matchTutorialMutations } from './tutorialScenario'
import { TutorialInstructionPanel } from './TutorialInstructionPanel'
import { TutorialShell } from './TutorialShell'
import { TutorialApiBoundary } from './TutorialApiBoundary'
import { TutorialLivePage } from './TutorialLivePage'
import { TutorialInteractionGuard } from './TutorialInteractionGuard'

export function TutorialWorkspace({ tutorial, onExit, onSkipTutorial, onContinueLater }) {
  const [reviewStepIndex, setReviewStepIndex] = useState(null)
  const instructionRef = useRef(null)
  const mountedRef = useRef(false)
  const reviewMode = Number.isInteger(reviewStepIndex)
  const screenStep = reviewMode ? TUTORIAL_STEPS[reviewStepIndex] : tutorial.currentStep

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true
      const focusTimer = window.setTimeout(() => instructionRef.current?.focus(), 0)
      return () => window.clearTimeout(focusTimer)
    }
    const resetTimer = window.setTimeout(() => {
      setReviewStepIndex(null)
      instructionRef.current?.focus()
    }, 0)
    return () => window.clearTimeout(resetTimer)
  }, [tutorial.stepId])

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
      onSkipStep={tutorial.skipStep}
      onContinueLater={onContinueLater}
      onCompleteStep={() => tutorial.onAction(screenStep.action.id)}
      persistenceError={tutorial.persistenceError}
    />
  )

  const handleDomainMutation = ({ method, path, body }) => {
    if (reviewMode) return
    const matches = matchTutorialMutations({ method, path, body })
    const matched = matchTutorialMutation({ stepId: screenStep.id, method, path, body })
    if (!matched || matched.expectedActionId !== screenStep.action.id) return

    const sequence = [matched]
    const sequenceStep = {
      subject_create: 'module_add',
      course_create: 'class_create',
      teacher_add: 'teacher_competency',
    }[screenStep.id]
    if (sequenceStep && Array.isArray(body?.modules) && body.modules.length > 0) {
      const nextMatch = matches.find((candidate) => candidate.stepId === sequenceStep)
      if (nextMatch) sequence.push(nextMatch)
    } else if (sequenceStep === 'class_create' && Array.isArray(body?.classes_config) && body.classes_config.length > 0) {
      const nextMatch = matches.find((candidate) => candidate.stepId === sequenceStep)
      if (nextMatch) sequence.push(nextMatch)
    } else if (sequenceStep === 'teacher_competency' && Array.isArray(body?.subject_ids) && body.subject_ids.length > 0) {
      const nextMatch = matches.find((candidate) => candidate.stepId === sequenceStep)
      if (nextMatch) sequence.push(nextMatch)
    }

    if (sequence.length > 1) {
      tutorial.completeActionSequence(sequence.map(({ expectedActionId, changes }) => ({ actionId: expectedActionId, changes })))
    } else {
      tutorial.onAction(matched.expectedActionId, matched.changes)
    }
  }

  return (
    <TutorialApiBoundary scenario={tutorial.scenario} onDomainMutation={handleDomainMutation}>
      <TutorialShell activeNavItem={screenStep.activeNavItem} panel={panel}>
        <TutorialInteractionGuard step={screenStep} reviewMode={reviewMode} onTargetAction={() => tutorial.onAction(screenStep.action.id)} />
        {reviewMode && <div className="tutorial-review-banner">Está a consultar um passo concluído. As ações estão bloqueadas e o checkpoint não muda.</div>}
        <div
          className={reviewMode ? 'tutorial-live-page is-reviewing' : 'tutorial-live-page'}
          inert={reviewMode ? '' : undefined}
          aria-hidden={reviewMode ? 'true' : undefined}
        >
          <TutorialLivePage step={screenStep} />
        </div>
      </TutorialShell>
    </TutorialApiBoundary>
  )
}
