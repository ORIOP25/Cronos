import { useEffect, useReducer } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOrganization } from '@clerk/react'
import { useOnboardingStatus, useCompleteOnboarding } from '../features/onboarding/data'
import { getApiErrorMessage } from '../utils/apiErrors'
import GuidedFormShell from '../components/GuidedFormShell'
import StatePanel from '../components/StatePanel'
import FeedbackBanner from '../components/FeedbackBanner'
import OnboardingQuestionnaire from '../features/onboarding/components/OnboardingQuestionnaire'
import { initialOnboardingState, onboardingReducer, validateOnboardingStep } from '../features/onboarding/onboardingModel'

export default function Onboarding() {
  const navigate = useNavigate()
  const { organization } = useOrganization()
  const statusQuery = useOnboardingStatus()
  const completeMutation = useCompleteOnboarding()
  const [state, dispatch] = useReducer(onboardingReducer, initialOnboardingState)
  const organizationName = statusQuery.data?.organization_name || organization?.name || 'a sua escola'

  useEffect(() => {
    if (statusQuery.data?.onboarding_complete) navigate('/dashboard', { replace: true })
  }, [navigate, statusQuery.data?.onboarding_complete])

  const handleComplete = async () => {
    const errors = validateOnboardingStep(2, state.values)
    if (Object.keys(errors).length) { dispatch({ type: 'SET_ERRORS', errors }); return }
    dispatch({ type: 'SUBMIT_STARTED' })
    try {
      await completeMutation.mutateAsync(state.values)
      dispatch({ type: 'SUBMIT_SUCCEEDED' })
    } catch (error) {
      dispatch({ type: 'SUBMIT_FAILED', error: getApiErrorMessage(error, 'Não foi possível guardar a configuração. Tente novamente.') })
    }
  }

  if (statusQuery.isLoading) return <div className="guided-form-shell"><StatePanel state="loading" title="A preparar a sua escola" description="Estamos a verificar a configuração inicial." /></div>
  if (statusQuery.isError) return <div className="guided-form-shell"><StatePanel state="error" title="Não foi possível carregar a configuração" action={<button type="button" className="btn btn-outline-primary" onClick={() => statusQuery.refetch()}>Tentar novamente</button>} /></div>
  if (statusQuery.data?.onboarding_complete) return <div className="guided-form-shell"><StatePanel state="loading" title="A abrir o Cronos" /></div>

  return (
    <GuidedFormShell
      eyebrow="Configuração inicial"
      title="Prepare o Cronos para a sua escola"
      summary={`Vamos preparar ${organizationName}. Depois, poderá configurar recursos e gerar horários.`}
      meta="2 passos, cerca de 1 minuto"
    >
      {state.error && <div className="mb-3"><FeedbackBanner tone="danger">{state.error}</FeedbackBanner></div>}
      <OnboardingQuestionnaire state={state} dispatch={dispatch} onSubmit={state.currentStep === 3 ? () => navigate('/dashboard', { replace: true }) : handleComplete} />
    </GuidedFormShell>
  )
}
