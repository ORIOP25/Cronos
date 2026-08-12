import { useCallback, useReducer, useRef, useState } from 'react'
import { useSubmitContact } from '../data'
import { getApiErrorMessage } from '../../../utils/apiErrors'
import { initialQuestionnaireState, questionnaireReducer, toContactPayload, validateQuestionnaireStep } from '../questionnaireModel'
import QuestionnaireProgress from './QuestionnaireProgress'
import QuestionnaireStep from './QuestionnaireStep'
import ContactSuccess from './ContactSuccess'

export default function ContactQuestionnaire() {
  const [state, dispatch] = useReducer(questionnaireReducer, initialQuestionnaireState)
  const [validationErrors, setValidationErrors] = useState({})
  const [turnstileResetVersion, setTurnstileResetVersion] = useState(0)
  const submittingReference = useRef(false)
  const submitContact = useSubmitContact()

  const setAnswer = useCallback((field, value) => {
    dispatch({ type: 'SET_ANSWER', field, value })
  }, [])

  const handleNext = useCallback(() => {
    const errors = validateQuestionnaireStep(state.currentStep, state.answers)
    setValidationErrors(errors)
    if (Object.keys(errors).length === 0) dispatch({ type: 'NEXT' })
  }, [state.answers, state.currentStep])

  const handleOption = useCallback((field, value) => {
    setAnswer(field, value)
    dispatch({ type: 'NEXT' })
  }, [setAnswer])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (state.status === 'submitting' || submittingReference.current) return
    if (!state.turnstileToken) {
      dispatch({ type: 'SUBMIT_FAILED', error: 'Confirme a verificação anti-spam antes de enviar o pedido.' })
      return
    }
    submittingReference.current = true
    dispatch({ type: 'SUBMIT_STARTED' })
    try {
      await submitContact.mutateAsync(toContactPayload(state))
      dispatch({ type: 'SUBMIT_SUCCEEDED' })
    } catch (error) {
      dispatch({ type: 'SUBMIT_FAILED', error: getApiErrorMessage(error, 'Não foi possível enviar o pedido neste momento.') })
      setTurnstileResetVersion((version) => version + 1)
    } finally {
      submittingReference.current = false
    }
  }

  const handleReset = () => {
    submittingReference.current = false
    dispatch({ type: 'RESET' })
    setValidationErrors({})
    setTurnstileResetVersion(0)
    submitContact.reset()
  }

  const handleTurnstileSuccess = useCallback((token) => {
    dispatch({ type: 'TURNSTILE_SUCCEEDED', token })
  }, [])

  const handleTurnstileExpired = useCallback(() => {
    dispatch({ type: 'TURNSTILE_EXPIRED' })
  }, [])

  const handleTurnstileError = useCallback((error) => {
    dispatch({ type: 'TURNSTILE_FAILED', error: error || undefined })
  }, [])

  const callbacks = {
    onOption: handleOption,
    onChange: setAnswer,
    onDetailsNext: (event) => {
      event.preventDefault()
      handleNext()
    },
    onWebsiteChange: (value) => setAnswer('website', value),
    onSubmit: handleSubmit,
    onTurnstileSuccess: handleTurnstileSuccess,
    onTurnstileExpired: handleTurnstileExpired,
    onTurnstileError: handleTurnstileError,
  }

  return (
    <section className="cronos-contact-page" aria-labelledby="cronos-contact-title">
      <div className="cronos-container cronos-contact-page__grid">
        <div className="cronos-contact-page__intro">
          <p className="cronos-eyebrow">Contacto</p>
          <h1 id="cronos-contact-title">Mostre-nos onde o horário está a falhar</h1>
          <p>5 passos, cerca de 1 minuto</p>
          <div className="cronos-contact-page__graphic" aria-hidden="true">
            <span /><span /><span /><span /><span />
          </div>
        </div>
        <div className="cronos-questionnaire">
          {state.currentStep === 0 && <Welcome onStart={() => dispatch({ type: 'START' })} />}
          {state.currentStep > 0 && state.currentStep <= 5 && <QuestionnaireProgress step={state.currentStep} pending={state.status === 'submitting'} onBack={() => dispatch({ type: 'BACK' })} />}
          <QuestionnaireStep step={state.currentStep} answers={state.answers} errors={validationErrors} state={{ ...state, turnstileResetVersion }} callbacks={callbacks} />
          {state.currentStep === 6 && <ContactSuccess name={state.successName} onReset={handleReset} />}
        </div>
      </div>
    </section>
  )
}

function Welcome({ onStart }) {
  return (
    <div className="cronos-questionnaire__welcome">
      <h2>Vamos perceber onde o horário está a falhar</h2>
      <p>Responda a cinco perguntas curtas para prepararmos a demonstração.</p>
      <button type="button" className="cronos-button" onClick={onStart}>Começar</button>
    </div>
  )
}
