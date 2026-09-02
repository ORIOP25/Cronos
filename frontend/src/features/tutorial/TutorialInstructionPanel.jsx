import { forwardRef } from 'react'
import {
  TUTORIAL_CHAPTERS,
  TUTORIAL_COPY,
  TUTORIAL_STEPS,
  getTutorialChapter,
  getTutorialStepNumber,
} from './tutorialContent'

export const TutorialInstructionPanel = forwardRef(function TutorialInstructionPanel({
  step,
  stepIndex,
  totalSteps,
  progressPercent,
  reviewMode,
  reviewStepIndex,
  onPrevious,
  onReturnToCurrent,
  onExit,
  onSkipTutorial,
  onAdvance,
  persistenceError,
}, ref) {
  const viewedIndex = reviewMode ? reviewStepIndex : stepIndex
  const isFirst = viewedIndex <= 0
  const isLast = !reviewMode && viewedIndex === totalSteps - 1
  const isChapterStart = viewedIndex === 0 || TUTORIAL_STEPS[viewedIndex - 1]?.chapter !== step.chapter
  const chapter = getTutorialChapter(step.chapter) || TUTORIAL_CHAPTERS[0]
  const stepNumber = getTutorialStepNumber(step.id) || viewedIndex + 1

  return (
    <aside className={`tutorial-instruction-panel${reviewMode ? ' is-reviewing' : ''}`} data-step-id={step.id} data-testid="tutorial-instruction-panel" aria-label="Instruções do guia">
      <div className="tutorial-chapter-label">Capítulo {step.chapter} · {chapter?.title}</div>
      <div className="tutorial-instruction-panel__progress" aria-label={`${progressPercent}% do guia concluído`}><span style={{ width: `${progressPercent}%` }} /></div>
      <div ref={ref} tabIndex="-1" className="tutorial-instruction-panel__copy" id="tutorial-instruction" aria-live="polite">
        {isChapterStart && <p className="tutorial-chapter-introduction">{chapter?.introduction}</p>}
        {!reviewMode && stepIndex === 0 && <p className="tutorial-initial-note" data-testid="tutorial-initial-note">{TUTORIAL_COPY.initialNote}</p>}
        {reviewMode && <p className="tutorial-review-label">{TUTORIAL_COPY.reviewLabel(reviewStepIndex + 1)}</p>}
        <p className="tutorial-step-counter" data-testid="tutorial-step-counter">Passo {stepNumber} de {totalSteps}</p>
        <h1>{step.title}</h1>
        <p className="tutorial-instruction-panel__description">{step.description}</p>
        {!reviewMode && (
          <div className="tutorial-instruction-panel__instruction">
            <span>{TUTORIAL_COPY.optionalAction}</span>
            <strong>{step.instruction}</strong>
          </div>
        )}
        {reviewMode && <div className="tutorial-instruction-panel__instruction"><span>Consulta</span><strong>Este passo apresenta um exemplo preparado.</strong></div>}
        {persistenceError && <div className="alert alert-warning mt-3" role="alert">{TUTORIAL_COPY.persistenceFailure}</div>}
      </div>
      <div className="tutorial-instruction-panel__controls">
        {reviewMode ? (
          <>
            <button type="button" className="tutorial-button tutorial-button--quiet" onClick={onPrevious} disabled={isFirst} data-testid="tutorial-prev-button">← Passo anterior</button>
            <button type="button" className="tutorial-button tutorial-button--primary" onClick={onReturnToCurrent}>{TUTORIAL_COPY.returnToCurrent}</button>
          </>
        ) : (
          <>
            <button type="button" className="tutorial-button tutorial-button--primary" onClick={onAdvance} data-testid="tutorial-advance-button">{isLast ? 'Concluir guia' : 'Continuar'}</button>
            <button type="button" className="tutorial-button tutorial-button--quiet" onClick={onPrevious} disabled={isFirst} data-testid="tutorial-prev-button">← Rever anterior</button>
          </>
        )}
      </div>
      <div className="tutorial-instruction-panel__footer">
        <button type="button" className="tutorial-link-button" onClick={onExit} data-testid="tutorial-exit-button">Sair do guia</button>
        {!reviewMode && <button type="button" className="tutorial-link-button tutorial-link-button--warning" onClick={onSkipTutorial} data-testid="tutorial-skip-all-button">Saltar guia</button>}
      </div>
    </aside>
  )
})
