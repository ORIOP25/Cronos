import { useState, memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilChevronLeft, cilChevronRight } from '@coreui/icons'
import { workflowSteps } from '../../data/marketingData'

const ProcessStepperSection = memo(function ProcessStepperSection() {
  const [activeStep, setActiveStep] = useState(0)
  const currentWorkflowStep = workflowSteps[activeStep]

  return (
    <section className="cronos-process" aria-labelledby="cronos-process-title">
      <div className="cronos-layout">
        <div className="cronos-process__intro">
          <div>
            <h2 id="cronos-process-title">Da preparação ao progresso UFCD</h2>
          </div>
          <p>
            Desenvolvemos o Cronos ao lado de coordenadores e diretores de escolas profissionais. Vimos de perto o cansaço de fechar mapas de UFCDs à mão e gerir substituições no WhatsApp. Por isso, desenhámos um fluxo natural que respeita as pessoas e o tempo de cada escola.
          </p>
        </div>

        {/* Interactive Stepper Navigation Bar */}
        <div className="cronos-stepper-container">
          <div className="cronos-stepper-track">
            <div
              className="cronos-stepper-progress-fill"
              style={{ width: `${((activeStep + 1) / workflowSteps.length) * 100}%` }}
            />
          </div>
          <div className="cronos-stepper-pills">
            {workflowSteps.map((step, idx) => {
              const isActive = idx === activeStep
              const isCompleted = idx < activeStep
              return (
                <button
                  key={step.number}
                  type="button"
                  className={`cronos-stepper-pill ${isActive ? 'is-active' : ''} ${isCompleted ? 'is-completed' : ''}`}
                  onClick={() => setActiveStep(idx)}
                  aria-label={`Ver Etapa ${step.number}: ${step.title}`}
                >
                  <span className="cronos-stepper-pill__number">{step.number}</span>
                  <span className="cronos-stepper-pill__title">{step.title}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Active Step Showcase Card */}
        <article className="cronos-step-showcase">
          <div className="cronos-step-showcase__content">
            <h3>{currentWorkflowStep.title}</h3>
            <p>{currentWorkflowStep.text}</p>
            <div className="cronos-step-showcase__nav">
              <button
                type="button"
                className="cronos-step-btn"
                disabled={activeStep === 0}
                onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
              >
                <CIcon icon={cilChevronLeft} /> Anterior
              </button>
              <button
                type="button"
                className="cronos-step-btn cronos-step-btn--next"
                disabled={activeStep === workflowSteps.length - 1}
                onClick={() => setActiveStep((prev) => Math.min(workflowSteps.length - 1, prev + 1))}
              >
                Seguinte <CIcon icon={cilChevronRight} />
              </button>
            </div>
          </div>
        </article>
      </div>
    </section>
  )
})

export default ProcessStepperSection
