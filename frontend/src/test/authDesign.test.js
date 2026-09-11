import { describe, expect, it } from 'vitest'
import { CLERK_LOCALIZATION_PT } from '../utils/authDesign'

describe('Clerk Portuguese localization', () => {
  it('keeps the auth entry points in Portuguese and aligned with Cronos copy', () => {
    expect(CLERK_LOCALIZATION_PT.signIn.start.title).toBe('Entrar no Cronos')
    expect(CLERK_LOCALIZATION_PT.signIn.start.subtitle).toBe('Bem-vindo de volta. Entre para continuar.')
    expect(CLERK_LOCALIZATION_PT.signIn.start.actionLink).toBe('Registar')
    expect(CLERK_LOCALIZATION_PT.signUp.start.title).toBe('Criar conta no Cronos')
    expect(CLERK_LOCALIZATION_PT.formFieldLabel__emailAddress).toBe('Email')
    expect(CLERK_LOCALIZATION_PT.formButtonPrimary).toBe('Continuar')
  })

  it('uses the checkbox as the only legal-consent sentence', () => {
    expect(CLERK_LOCALIZATION_PT.signUp.legalConsent.continue.subtitle).toBe('')
    expect(CLERK_LOCALIZATION_PT.signUp.legalConsent.checkbox.label__termsOfServiceAndPrivacyPolicy).toContain('Ao criar uma escola')
  })
})
