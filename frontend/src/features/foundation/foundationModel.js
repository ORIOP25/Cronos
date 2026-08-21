export const FOUNDATION_STEP_COUNT = 9

export const STEP_PERIOD = 1
export const STEP_DAYS = 2
export const STEP_OPENING = 3
export const STEP_SLOT_DURATION = 4
export const STEP_BREAK_DURATION = 5
export const STEP_LUNCH = 6
export const STEP_PREVIEW = 7
export const STEP_CALENDAR = 8
export const STEP_CONFIRMATION = 9

export const STEP_LABELS = [
  'Período Escolar',
  'Dias Letivos',
  'Horário de Funcionamento',
  'Duração do Bloco',
  'Intervalos',
  'Almoço',
  'Grelha Gerada',
  'Pausas e Feriados',
  'Ativação',
]

export const initialFoundationDraftValues = {
  school_start_date: '',
  school_hard_end_date: '',
  repair_stability_window_days: 14,
  days_of_week: [0, 1, 2, 3, 4],
  opening_time: '08:30',
  closing_time: '17:30',
  slot_duration_minutes: 50,
  break_duration_minutes: 10,
  lunch_window_start: '12:30',
  lunch_window_end: '14:00',
  lunch_min_duration_minutes: 60,
}

export const initialFoundationState = {
  currentStep: 1,
  version: 0,
  values: initialFoundationDraftValues,
  fieldErrors: {},
  status: 'idle', // 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
  error: '',
  conflictData: null,
  completedThisSession: false,
}

export function timeToMinutes(val) {
  if (!val) return NaN
  const parts = String(val).split(':').map(Number)
  if (parts.length < 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) return NaN
  return parts[0] * 60 + parts[1]
}

export function minutesToTime(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60)
  const mins = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

export function calculateGridSlots(values) {
  const openMin = timeToMinutes(values.opening_time)
  const closeMin = timeToMinutes(values.closing_time)
  const slotDur = values.slot_duration_minutes == null ? 50 : Number(values.slot_duration_minutes)
  const breakDur = values.break_duration_minutes == null ? 10 : Number(values.break_duration_minutes)
  const lunchStart = timeToMinutes(values.lunch_window_start)
  const lunchEnd = timeToMinutes(values.lunch_window_end)

  if (Number.isNaN(openMin) || Number.isNaN(closeMin) || closeMin <= openMin) {
    return []
  }

  const slots = []
  let cur = openMin
  let slotIndex = 1

  while (cur + slotDur <= closeMin) {
    const slotEnd = cur + slotDur

    // If overlaps lunch window
    const inLunch =
      !Number.isNaN(lunchStart) &&
      !Number.isNaN(lunchEnd) &&
      cur < lunchEnd &&
      slotEnd > lunchStart

    if (inLunch) {
      cur = Math.max(cur + breakDur, lunchEnd)
      continue
    }

    slots.push({
      index: slotIndex++,
      start: minutesToTime(cur),
      end: minutesToTime(slotEnd),
    })

    cur = slotEnd + breakDur
  }

  return slots
}

export function validateFoundationStep(step, values) {
  const errors = {}

  if (step === STEP_PERIOD) {
    if (!values.school_start_date) {
      errors.school_start_date = 'Indique a data de início do ano letivo.'
    }
    if (!values.school_hard_end_date) {
      errors.school_hard_end_date = 'Indique a data-limite rígida.'
    }
    if (
      values.school_start_date &&
      values.school_hard_end_date &&
      values.school_hard_end_date <= values.school_start_date
    ) {
      errors.school_hard_end_date = 'A data-limite deve ser posterior à data de início.'
    }
    const windowDays = Number(values.repair_stability_window_days)
    if (!Number.isInteger(windowDays) || windowDays < 1 || windowDays > 60) {
      errors.repair_stability_window_days = 'A janela de estabilidade deve estar entre 1 e 60 dias.'
    }
  }

  if (step === STEP_DAYS) {
    if (
      !Array.isArray(values.days_of_week) ||
      values.days_of_week.length === 0 ||
      values.days_of_week.some((day) => !Number.isInteger(Number(day)) || Number(day) < 0 || Number(day) > 6) ||
      new Set(values.days_of_week).size !== values.days_of_week.length
    ) {
      errors.days_of_week = 'Selecione pelo menos um dia de aulas na semana.'
    }
  }

  if (step === STEP_OPENING) {
    const openMin = timeToMinutes(values.opening_time)
    const closeMin = timeToMinutes(values.closing_time)
    if (Number.isNaN(openMin)) errors.opening_time = 'Indique a hora de abertura da escola.'
    if (Number.isNaN(closeMin)) errors.closing_time = 'Indique a hora de fecho da escola.'
    if (!Number.isNaN(openMin) && !Number.isNaN(closeMin) && closeMin <= openMin) {
      errors.closing_time = 'A hora de fecho deve ser posterior à hora de abertura.'
    }
  }

  if (step === STEP_SLOT_DURATION) {
    const slotDur = Number(values.slot_duration_minutes)
    if (!Number.isInteger(slotDur) || slotDur < 15 || slotDur > 120) {
      errors.slot_duration_minutes = 'A duração do bloco deve ser entre 15 e 120 minutos.'
    }
  }

  if (step === STEP_BREAK_DURATION) {
    const breakDur = Number(values.break_duration_minutes)
    if (!Number.isInteger(breakDur) || breakDur < 0 || breakDur > 60) {
      errors.break_duration_minutes = 'O intervalo deve ser entre 0 e 60 minutos.'
    }
  }

  if (step === STEP_LUNCH) {
    const lunchStartMin = timeToMinutes(values.lunch_window_start)
    const lunchEndMin = timeToMinutes(values.lunch_window_end)
    const lunchDur = Number(values.lunch_min_duration_minutes)

    if (Number.isNaN(lunchStartMin)) errors.lunch_window_start = 'Indique o início do período de almoço.'
    if (Number.isNaN(lunchEndMin)) errors.lunch_window_end = 'Indique o fim do período de almoço.'
    if (!Number.isNaN(lunchStartMin) && !Number.isNaN(lunchEndMin) && lunchEndMin <= lunchStartMin) {
      errors.lunch_window_end = 'O fim do almoço deve ser posterior ao início.'
    }
    if (!Number.isInteger(lunchDur) || lunchDur < 15) {
      errors.lunch_min_duration_minutes = 'A duração mínima de almoço deve ser pelo menos 15 minutos.'
    }
    if (
      !Number.isNaN(lunchStartMin) &&
      !Number.isNaN(lunchEndMin) &&
      Number.isInteger(lunchDur) &&
      lunchDur > lunchEndMin - lunchStartMin
    ) {
      errors.lunch_min_duration_minutes = 'A duração mínima de almoço não pode exceder o intervalo de almoço.'
    }
    const openingMin = timeToMinutes(values.opening_time)
    const closingMin = timeToMinutes(values.closing_time)
    if (!Number.isNaN(openingMin) && !Number.isNaN(lunchStartMin) && lunchStartMin < openingMin) {
      errors.lunch_window_start = 'O almoço deve começar dentro do horário da escola.'
    }
    if (!Number.isNaN(closingMin) && !Number.isNaN(lunchEndMin) && lunchEndMin > closingMin) {
      errors.lunch_window_end = 'O almoço deve terminar dentro do horário da escola.'
    }
  }

  if (step === STEP_PREVIEW) {
    const slots = calculateGridSlots(values)
    if (slots.length === 0) {
      errors.preview = 'A configuração atual não permite gerar nenhum bloco de horário.'
    }
  }

  if (step === STEP_CONFIRMATION) {
    // Cumulative check for all preceding steps
    for (let s = 1; s <= STEP_LUNCH; s++) {
      const stepErrs = validateFoundationStep(s, values)
      Object.assign(errors, stepErrs)
    }
  }

  return errors
}

export function foundationReducer(state, action) {
  switch (action.type) {
    case 'INIT_FROM_SERVER': {
      const serverDraft = action.payload || {}
      return {
        ...state,
        version: serverDraft.version || 0,
        currentStep: serverDraft.current_step || 1,
        values: {
          ...initialFoundationDraftValues,
          ...(serverDraft.data || {}),
        },
        fieldErrors: {},
        status: 'idle',
        error: '',
      }
    }

    case 'SET_FIELD':
      return {
        ...state,
        values: { ...state.values, [action.field]: action.value },
        fieldErrors: { ...state.fieldErrors, [action.field]: '' },
        error: '',
      }

    case 'SET_ERRORS':
      return {
        ...state,
        fieldErrors: action.errors,
      }

    case 'SET_STEP':
      return {
        ...state,
        currentStep: action.step,
        fieldErrors: {},
      }

    case 'NEXT_STEP':
      return {
        ...state,
        currentStep: Math.min(FOUNDATION_STEP_COUNT, state.currentStep + 1),
        fieldErrors: {},
      }

    case 'PREV_STEP':
      return {
        ...state,
        currentStep: Math.max(1, state.currentStep - 1),
        fieldErrors: {},
        error: '',
      }

    case 'SAVE_STARTED':
      return {
        ...state,
        status: 'saving',
      }

    case 'SAVE_SUCCEEDED':
      return {
        ...state,
        status: 'saved',
        version: action.version ?? state.version + 1,
      }

    case 'SAVE_FAILED':
      return {
        ...state,
        status: 'error',
        error: action.error,
      }

    case 'VERSION_CONFLICT':
      return {
        ...state,
        status: 'conflict',
        conflictData: action.payload,
        error: 'Conflito de versão: o rascunho foi modificado noutra sessão.',
      }

    case 'RESOLVE_CONFLICT_RELOAD': {
      const latest = action.payload
      return {
        ...state,
        status: 'idle',
        conflictData: null,
        error: '',
        version: latest.version,
        currentStep: latest.current_step || state.currentStep,
        values: {
          ...initialFoundationDraftValues,
          ...(latest.data || {}),
        },
      }
    }

    case 'RESOLVE_CONFLICT_OVERRIDE':
      return state

    case 'CLOSE_CONFLICT':
      return {
        ...state,
        status: 'idle',
        conflictData: null,
        error: '',
      }

    case 'COMPLETE_STARTED':
      return {
        ...state,
        status: 'saving',
        error: '',
      }

    case 'COMPLETE_SUCCEEDED':
      return {
        ...state,
        status: 'saved',
        completedThisSession: true,
      }

    case 'COMPLETE_FAILED':
      return {
        ...state,
        status: 'error',
        error: action.error,
      }

    default:
      return state
  }
}
