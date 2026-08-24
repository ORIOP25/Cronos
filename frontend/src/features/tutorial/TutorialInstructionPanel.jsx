import { forwardRef } from 'react'

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
  onSkipStep,
  onContinueLater,
  onCompleteStep,
  persistenceError,
}, ref) {
  const viewedIndex = reviewMode ? reviewStepIndex : stepIndex
  const isFirst = viewedIndex <= 0
  return (
    <aside className={`tutorial-instruction-panel${reviewMode ? ' is-reviewing' : ''}`} data-step-id={step.id} data-testid="tutorial-instruction-panel" aria-label="Instruções do guia">
      <div className="tutorial-instruction-panel__topline"><span>Ambiente de demonstração</span><span className="tutorial-instruction-panel__dot">●</span></div>
      <div className="tutorial-chapter-label">Capítulo {step.chapter} · {step.chapter === 1 ? 'Fundação e bases' : 'Planeamento e operação'}</div>
      <div className="tutorial-instruction-panel__progress"><span style={{ width: `${progressPercent}%` }} /></div>
      <div ref={ref} tabIndex="-1" className="tutorial-instruction-panel__copy" id="tutorial-instruction">
        {reviewMode && <p className="tutorial-review-label">A rever o passo {reviewStepIndex + 1}</p>}
        <p className="tutorial-step-counter" data-testid="tutorial-step-counter">Passo {viewedIndex + 1} de {totalSteps}</p>
        <h1>{step.title}</h1>
        <p className="tutorial-instruction-panel__description">{step.description}</p>
        <div className="tutorial-instruction-panel__instruction"><span>Próxima ação</span><strong>{reviewMode ? 'Consulta apenas' : step.instruction}</strong></div>
        {persistenceError && <div className="alert alert-warning mt-3" role="alert">O progresso está apenas em memória e não será retomável: não foi possível guardar no dispositivo.</div>}
      </div>
      <div className="tutorial-instruction-panel__controls">
        {reviewMode ? (
          <>
            <button type="button" className="tutorial-button tutorial-button--quiet" onClick={onPrevious} disabled={isFirst} data-testid="tutorial-prev-button">← Passo anterior</button>
            <button type="button" className="tutorial-button tutorial-button--primary" onClick={onReturnToCurrent}>Voltar ao passo atual</button>
          </>
        ) : (
          <>
            {step.completion === 'panel' && <button type="button" className="tutorial-button tutorial-button--primary" onClick={onCompleteStep} data-testid="tutorial-complete-step">{step.action.label}</button>}
            <button type="button" className="tutorial-button tutorial-button--quiet" onClick={onPrevious} disabled={isFirst} data-testid="tutorial-prev-button">← Anterior</button>
          </>
        )}
        {!reviewMode && step.id === 'chapter_transition' && <button type="button" className="tutorial-link-button" onClick={onContinueLater} data-testid="tutorial-continue-later-button">Continuar mais tarde</button>}
        {!reviewMode && step.isSkippable && step.id !== 'chapter_transition' && <button type="button" className="tutorial-link-button" onClick={onSkipStep} data-testid="tutorial-skip-step-button">Saltar este passo</button>}
      </div>
      <div className="tutorial-instruction-panel__footer">
        <button type="button" className="tutorial-link-button" onClick={onExit} data-testid="tutorial-exit-button">Sair do guia</button>
        {!reviewMode && <button type="button" className="tutorial-link-button tutorial-link-button--warning" onClick={onSkipTutorial} data-testid="tutorial-skip-all-button">Saltar guia</button>}
      </div>
    </aside>
  )
})
