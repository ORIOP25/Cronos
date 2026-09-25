import { normalizeTimeOfDay, timeOfDayToMinutes } from '../../utils/timeOfDay'

export const FOUNDATION_STEP_COUNT = 9

const TIME_FIELDS = new Set([
  'opening_time',
  'closing_time',
  'lunch_window_start',
  'lunch_window_end',
])

export const STEP_PERIOD = 1
export const STEP_DAYS = 2
export const STEP_OPENING = 3
export const STEP_SLOT_DURATION = 4
export const STEP_BREAK_DURATION = 5
export const STEP_LUNCH = 6
export const STEP_PREVIEW = 7
export const STEP_CALENDAR = 8
export const STEP_CONFIRMATION = 9

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
  automatic_holidays_enabled: false,
}

export const initialFoundationState = {
  currentStep: 1,
  version: 0,
  values: initialFoundationDraftValues,
  fieldErrors: {},
  status: 'idle', // 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
  error: '',
  errorCode: '',
  conflictData: null,
  completedThisSession: false,
}

export function minutesToTime(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60)
  const mins = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

export function serializeFoundationDraftValues(values) {
  return Object.fromEntries(Object.entries(values).map(([field, value]) => {
    if (field === 'repair_stability_window_days') {
      return [field, value === '' || value == null ? 0 : Number(value)]
    }
    if (TIME_FIELDS.has(field)) {
      return [field, value === '' || value == null ? null : normalizeTimeOfDay(value)]
    }
    return [field, value === '' ? null : value]
  }))
}

export function buildDailyTimeslots(values) {
  const openMin = timeOfDayToMinutes(values.opening_time)
  const closeMin = timeOfDayToMinutes(values.closing_time)
  const slotDur = values.slot_duration_minutes == null ? 50 : Number(values.slot_duration_minutes)
  const breakDur = values.break_duration_minutes == null ? 10 : Number(values.break_duration_minutes)

  if (
    Number.isNaN(openMin) ||
    Number.isNaN(closeMin) ||
    closeMin <= openMin ||
    !Number.isInteger(slotDur) ||
    !Number.isInteger(breakDur) ||
    slotDur <= 0 ||
    breakDur < 0
  ) {
    return []
  }

  const slots = []
  let cur = openMin
  let slotIndex = 1

  while (cur + slotDur <= closeMin) {
    const slotEnd = cur + slotDur

    slots.push({
      id: `${minutesToTime(cur)}-${minutesToTime(slotEnd)}`,
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
    const rawWindowDays = values.repair_stability_window_days
    const windowDays = rawWindowDays === '' || rawWindowDays == null ? 0 : Number(rawWindowDays)
    if (!Number.isInteger(windowDays) || windowDays < 0 || windowDays > 60) {
      errors.repair_stability_window_days = 'A janela de estabilidade deve estar entre 0 e 60 dias.'
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
    const openMin = timeOfDayToMinutes(values.opening_time)
    const closeMin = timeOfDayToMinutes(values.closing_time)
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
    const lunchStartMin = timeOfDayToMinutes(values.lunch_window_start)
    const lunchEndMin = timeOfDayToMinutes(values.lunch_window_end)
    const lunchDur = Number(values.lunch_min_duration_minutes)

    if (Number.isNaN(lunchStartMin)) errors.lunch_window_start = 'Indique o início do período de almoço.'
    if (Number.isNaN(lunchEndMin)) errors.lunch_window_end = 'Indique o fim do período de almoço.'
    if (!Number.isNaN(lunchStartMin) && !Number.isNaN(lunchEndMin) && lunchEndMin <= lunchStartMin) {
      errors.lunch_window_end = 'O fim do almoço deve ser posterior ao início.'
    }
    if (!Number.isInteger(lunchDur) || lunchDur < 1) {
      errors.lunch_min_duration_minutes = 'A duração mínima de almoço deve ser pelo menos 1 minuto.'
    }
    if (
      !Number.isNaN(lunchStartMin) &&
      !Number.isNaN(lunchEndMin) &&
      Number.isInteger(lunchDur) &&
      lunchDur > lunchEndMin - lunchStartMin
    ) {
      errors.lunch_min_duration_minutes = 'A duração mínima de almoço não pode exceder o intervalo de almoço.'
    }
    const openingMin = timeOfDayToMinutes(values.opening_time)
    const closingMin = timeOfDayToMinutes(values.closing_time)
    if (!Number.isNaN(openingMin) && !Number.isNaN(lunchStartMin) && lunchStartMin < openingMin) {
      errors.lunch_window_start = 'O almoço deve começar dentro do horário da escola.'
    }
    if (!Number.isNaN(closingMin) && !Number.isNaN(lunchEndMin) && lunchEndMin > closingMin) {
      errors.lunch_window_end = 'O almoço deve terminar dentro do horário da escola.'
    }
  }

  if (step === STEP_PREVIEW) {
    const slots = buildDailyTimeslots(values)
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
      const serverValues = Object.fromEntries(
        Object.entries(serverDraft.data || {}).filter(([, value]) => value !== null && value !== undefined),
      )
      return {
        ...state,
        version: serverDraft.version || 0,
        currentStep: serverDraft.current_step || 1,
        values: {
          ...initialFoundationDraftValues,
          ...serverValues,
        },
        fieldErrors: {},
        status: 'idle',
        error: '',
        errorCode: '',
      }
    }

    case 'SET_FIELD':
      return {
        ...state,
        values: { ...state.values, [action.field]: action.value },
        fieldErrors: { ...state.fieldErrors, [action.field]: '' },
        error: '',
        errorCode: '',
      }

    case 'SET_ERRORS':
      return {
        ...state,
        fieldErrors: action.errors,
        error: '',
        errorCode: '',
      }

    case 'SET_STEP':
      return {
        ...state,
        currentStep: action.step,
        fieldErrors: {},
        error: '',
        errorCode: '',
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
        errorCode: '',
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
        error: '',
        errorCode: '',
        version: action.version ?? state.version + 1,
      }

    case 'SAVE_FAILED':
      return {
        ...state,
        status: 'error',
        error: action.error,
        errorCode: action.errorCode || '',
      }

    case 'VERSION_CONFLICT':
      return {
        ...state,
        status: 'conflict',
        conflictData: action.payload,
        error: 'Conflito de versão: o rascunho foi modificado noutra sessão.',
        errorCode: action.payload?.code || '',
      }

    case 'RESOLVE_CONFLICT_RELOAD': {
      const latest = action.payload
      return {
        ...state,
        status: 'idle',
        conflictData: null,
        error: '',
        errorCode: '',
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
        errorCode: '',
      }

    case 'COMPLETE_STARTED':
      return {
        ...state,
        status: 'saving',
        error: '',
        errorCode: '',
      }

    case 'COMPLETE_SUCCEEDED':
      return {
        ...state,
        status: 'saved',
        error: '',
        errorCode: '',
        completedThisSession: true,
      }

    case 'COMPLETE_FAILED':
      return {
        ...state,
        status: 'error',
        error: action.error,
        errorCode: action.errorCode || '',
      }

    default:
      return state
  }
}
