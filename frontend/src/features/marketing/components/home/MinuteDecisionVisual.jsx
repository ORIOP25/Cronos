import { useState } from 'react'
import { minuteWorkflow } from '../../content/home'

export default function MinuteDecisionVisual() {
  const [activeId, setActiveId] = useState(minuteWorkflow[0].id)
  const activeIndex = minuteWorkflow.findIndex((step) => step.id === activeId)
  const activeStep = minuteWorkflow[activeIndex]

  return (
    <div className="cronos-minute-visual" style={{ '--active-step': activeIndex }}>
      <div className="cronos-minute-visual__clock" aria-hidden="true">
        <span className="cronos-minute-visual__hand" />
        <span className="cronos-minute-visual__centre" />
        <span className="cronos-minute-visual__time">00:{[20, 40, 59][activeIndex]}</span>
      </div>
      <div className="cronos-minute-visual__content" aria-live="polite">
        <span className="cronos-minute-visual__index">0{activeIndex + 1}</span>
        <h3>{activeStep.title}</h3>
        <p>{activeStep.text}</p>
      </div>
      <div className="cronos-minute-visual__controls" aria-label="Passos da substituição">
        {minuteWorkflow.map((step, index) => (
          <button
            key={step.id}
            type="button"
            className={step.id === activeId ? 'is-active' : ''}
            aria-pressed={step.id === activeId}
            aria-label={`Passo ${index + 1}: ${step.title}`}
            onClick={() => setActiveId(step.id)}
          >
            <span>0{index + 1}</span>
            {step.title}
          </button>
        ))}
      </div>
    </div>
  )
}
