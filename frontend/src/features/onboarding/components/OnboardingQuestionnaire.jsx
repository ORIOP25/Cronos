import { useEffect } from 'react'
import GuidedFormProgress from '../../../components/GuidedFormProgress'
import AcademicYearStep from './AcademicYearStep'
import LunchWindowStep from './LunchWindowStep'
import { validateOnboardingStep } from '../onboardingModel'

export default function OnboardingQuestionnaire({ state, dispatch, onSubmit }) {
  useEffect(() => {
    if (Object.keys(state.fieldErrors).length === 0) return
    document.querySelector('[aria-invalid="true"]')?.focus()
  }, [state.fieldErrors])

  if (state.currentStep === 0) {
    return <div className="guided-form__body"><div><h2 className="guided-form__heading">Vamos preparar o ano letivo</h2><p className="guided-form__hint">As datas e a pausa de almoço são necessárias para gerar horários.</p></div><div className="guided-form__actions"><span /><button type="button" className="guided-form__primary" onClick={() => dispatch({ type: 'START' })}>Começar</button></div></div>
  }
  if (state.currentStep === 3) {
    return <div className="guided-form__success"><span className="guided-form__success-icon" aria-hidden="true">✓</span><h2 className="guided-form__heading">Configuração concluída</h2><p className="guided-form__hint">A organização pode agora configurar recursos e gerar horários.</p><button type="button" className="guided-form__primary" onClick={onSubmit}>Entrar no Cronos</button></div>
  }
  return <><GuidedFormProgress current={state.currentStep} total={2} onBack={state.currentStep === 2 ? () => dispatch({ type: 'BACK' }) : undefined} backDisabled={state.status === 'pending'} />{state.currentStep === 1 ? <AcademicYearStep values={state.values} errors={state.fieldErrors} onChange={(field, value) => dispatch({ type: 'SET_FIELD', field, value })} onNext={(event) => { event.preventDefault(); const errors = validateStep(1, state, dispatch); if (!Object.keys(errors).length) dispatch({ type: 'NEXT' }) }} /> : <LunchWindowStep values={state.values} errors={state.fieldErrors} onChange={(field, value) => dispatch({ type: 'SET_FIELD', field, value })} onBack={() => dispatch({ type: 'BACK' })} onSubmit={(event) => { event.preventDefault(); const errors = validateStep(2, state, dispatch); if (!Object.keys(errors).length) onSubmit() }} pending={state.status === 'pending'} />}</>
}

function validateStep(step, state, dispatch) {
  const errors = validateOnboardingStep(step, state.values)
  dispatch({ type: 'SET_ERRORS', errors })
  return errors
}
