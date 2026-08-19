export const ONBOARDING_STEP_COUNT = 2

export const initialOnboardingValues = {
  school_start_date: '',
  school_hard_end_date: '',
  lunch_start: '12:30',
  lunch_end: '14:00',
  lunch_min_duration: 60,
}

export const initialOnboardingState = {
  currentStep: 0,
  values: initialOnboardingValues,
  fieldErrors: {},
  status: 'idle',
  error: '',
  completedThisSession: false,
}

function minutes(value) {
  const [hours, mins] = String(value || '').split(':').map(Number)
  return Number.isFinite(hours) && Number.isFinite(mins) ? hours * 60 + mins : NaN
}

export function validateOnboardingStep(step, values) {
  const errors = {}
  if (step === 1) {
    if (!values.school_start_date) errors.school_start_date = 'Indique a data de início.'
    if (!values.school_hard_end_date) errors.school_hard_end_date = 'Indique a data-limite.'
    if (values.school_start_date && values.school_hard_end_date && values.school_hard_end_date <= values.school_start_date) {
      errors.school_hard_end_date = 'A data-limite deve ser posterior à data de início.'
    }
  }
  if (step === 2) {
    const start = minutes(values.lunch_start)
    const end = minutes(values.lunch_end)
    const duration = Number(values.lunch_min_duration)
    if (!values.lunch_start) errors.lunch_start = 'Indique a hora de início.'
    if (!values.lunch_end) errors.lunch_end = 'Indique a hora de fim.'
    if (Number.isFinite(start) && Number.isFinite(end) && end <= start) errors.lunch_end = 'A hora de fim deve ser posterior à hora de início.'
    if (!Number.isInteger(duration) || duration < 1) errors.lunch_min_duration = 'A duração deve ser um número inteiro de pelo menos 1 minuto.'
    if (Number.isFinite(start) && Number.isFinite(end) && Number.isInteger(duration) && duration > end - start) errors.lunch_min_duration = 'A duração não pode exceder a janela de almoço.'
  }
  return errors
}

export function onboardingReducer(state, action) {
  switch (action.type) {
    case 'START': return { ...state, currentStep: 1, fieldErrors: {}, error: '' }
    case 'SET_FIELD': return { ...state, values: { ...state.values, [action.field]: action.value }, fieldErrors: { ...state.fieldErrors, [action.field]: '' }, error: '' }
    case 'SET_ERRORS': return { ...state, fieldErrors: action.errors }
    case 'NEXT': return { ...state, currentStep: Math.min(ONBOARDING_STEP_COUNT, state.currentStep + 1), fieldErrors: {} }
    case 'BACK': return { ...state, currentStep: Math.max(1, state.currentStep - 1), fieldErrors: {}, status: 'idle', error: '' }
    case 'SUBMIT_STARTED': return { ...state, status: 'pending', error: '' }
    case 'SUBMIT_FAILED': return { ...state, status: 'error', error: action.error }
    case 'SUBMIT_SUCCEEDED': return { ...state, status: 'success', currentStep: ONBOARDING_STEP_COUNT + 1, completedThisSession: true, fieldErrors: {} }
    default: return state
  }
}
