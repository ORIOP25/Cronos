import { describe, it, expect } from 'vitest'
import { applyPortugueseValidity, clearPortugueseValidity } from '../utils/formValidity'

const input = (validityState) => {
  const element = document.createElement('input')
  Object.defineProperty(element, 'validity', { value: validityState, configurable: true })
  return { currentTarget: element }
}

describe('formValidity', () => {
  it('replaces the native message with Portuguese text', () => {
    const required = input({ valueMissing: true })
    applyPortugueseValidity(required)
    expect(required.currentTarget.validationMessage).toBe('Preencha este campo.')
    expect(required.currentTarget.getAttribute('aria-invalid')).toBe('true')

    const range = input({ rangeUnderflow: true })
    applyPortugueseValidity(range)
    expect(range.currentTarget.validationMessage).toBe('Indique um valor dentro do intervalo permitido.')

    const step = input({ stepMismatch: true })
    applyPortugueseValidity(step)
    expect(step.currentTarget.validationMessage).toBe('Indique um valor válido.')
  })

  it('clears the custom message when the field changes', () => {
    const event = input({ valueMissing: true })
    applyPortugueseValidity(event)
    clearPortugueseValidity(event)
    expect(event.currentTarget.validationMessage).toBe('')
    expect(event.currentTarget.hasAttribute('aria-invalid')).toBe(false)
  })
})
