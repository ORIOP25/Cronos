export const QUESTIONNAIRE_STEP_COUNT = 5

export const initialQuestionnaireState = {
  currentStep: 0,
  answers: { subject: '', courses: '', teachers: '', name: '', email: '', phone: '', message: '', website: '' },
  turnstileToken: '',
  status: 'idle',
  error: '',
  successName: '',
}

function clampStep(step) {
  return Math.max(0, Math.min(QUESTIONNAIRE_STEP_COUNT + 1, step))
}

export function questionnaireReducer(state, action) {
  switch (action.type) {
    case 'START': return { ...state, currentStep: 1, status: 'active', error: '' }
    case 'SET_ANSWER': return { ...state, answers: { ...state.answers, [action.field]: action.value }, error: '' }
    case 'NEXT': return { ...state, currentStep: clampStep(state.currentStep + 1), error: '' }
    case 'BACK': return { ...state, currentStep: clampStep(state.currentStep - 1), turnstileToken: state.currentStep === QUESTIONNAIRE_STEP_COUNT ? '' : state.turnstileToken, error: '' }
    case 'TURNSTILE_SUCCEEDED': return { ...state, turnstileToken: action.token, error: '' }
    case 'TURNSTILE_EXPIRED': return { ...state, turnstileToken: '', error: '' }
    case 'TURNSTILE_FAILED': return { ...state, turnstileToken: '', error: action.error || 'Não foi possível concluir a verificação anti-spam.' }
    case 'SUBMIT_STARTED': return { ...state, status: 'submitting', error: '' }
    case 'SUBMIT_SUCCEEDED': return { ...state, currentStep: QUESTIONNAIRE_STEP_COUNT + 1, status: 'success', successName: state.answers.name, turnstileToken: '', error: '' }
    case 'SUBMIT_FAILED': return { ...state, status: 'active', turnstileToken: '', error: action.error || 'Não foi possível enviar o pedido neste momento.' }
    case 'RESET': return initialQuestionnaireState
    default: return state
  }
}

export function validateQuestionnaireStep(step, answers) {
  const errors = {}
  if (step === 1 && !answers.subject) errors.subject = 'Selecione o principal desafio da escola.'
  if (step === 2 && !answers.courses) errors.courses = 'Selecione o número de cursos.'
  if (step === 3 && !answers.teachers) errors.teachers = 'Selecione o número de professores.'
  if (step === 4) {
    if (!answers.name.trim()) errors.name = 'Indique o seu nome.'
    if (!answers.email.trim()) errors.email = 'Indique o seu email.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(answers.email)) errors.email = 'Indique um email válido.'
  }
  return errors
}

export function toContactPayload(state) {
  return { ...state.answers, turnstile_token: state.turnstileToken }
}
