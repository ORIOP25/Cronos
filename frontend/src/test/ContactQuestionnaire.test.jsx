import { describe, expect, it } from 'vitest'
import { initialQuestionnaireState, questionnaireReducer, toContactPayload, validateQuestionnaireStep } from '../features/contact/questionnaireModel'

describe('questionnaire model', () => {
  it('keeps answers on back and clamps the step', () => {
    const started = questionnaireReducer(initialQuestionnaireState, { type: 'START' })
    const answered = questionnaireReducer(started, { type: 'SET_ANSWER', field: 'subject', value: 'Outro' })
    const next = questionnaireReducer(answered, { type: 'NEXT' })
    const back = questionnaireReducer(next, { type: 'BACK' })
    expect(back.currentStep).toBe(1)
    expect(back.answers.subject).toBe('Outro')
    expect(questionnaireReducer(initialQuestionnaireState, { type: 'BACK' }).currentStep).toBe(0)
  })

  it('validates required choices and contact details', () => {
    expect(validateQuestionnaireStep(1, initialQuestionnaireState.answers)).toEqual({ subject: 'Selecione o principal desafio da escola.' })
    expect(validateQuestionnaireStep(4, initialQuestionnaireState.answers)).toMatchObject({ name: 'Indique o seu nome.', email: 'Indique o seu email.' })
    expect(validateQuestionnaireStep(4, { ...initialQuestionnaireState.answers, name: 'Ana', email: 'invalid' })).toEqual({ email: 'Indique um email válido.' })
  })

  it('preserves the public snake_case payload contract', () => {
    const state = { ...initialQuestionnaireState, answers: { ...initialQuestionnaireState.answers, name: 'Ana', email: 'ana@example.com' }, turnstileToken: 'token' }
    expect(toContactPayload(state)).toEqual({ ...state.answers, turnstile_token: 'token' })
  })

  it('clears the token after a failed submission and resets exactly', () => {
    const state = { ...initialQuestionnaireState, currentStep: 5, turnstileToken: 'token', answers: { ...initialQuestionnaireState.answers, name: 'Ana' } }
    const failed = questionnaireReducer(state, { type: 'SUBMIT_FAILED', error: 'Erro' })
    expect(failed.turnstileToken).toBe('')
    expect(failed.answers.name).toBe('Ana')
    expect(questionnaireReducer(failed, { type: 'RESET' })).toEqual(initialQuestionnaireState)
  })
})
