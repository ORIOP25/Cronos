import { randomBytes } from 'node:crypto'
import { observeAcceptanceRuntime } from '../utils/acceptance-runtime.js'
import { test, expect } from './fixtures.js'

async function expectIdentity(page, email) {
  await expect.poll(() => page.evaluate(() => ({
    email: window.Clerk?.user?.primaryEmailAddress?.emailAddress,
    verified: window.Clerk?.user?.primaryEmailAddress?.verification?.status,
    session: Boolean(window.Clerk?.session),
  }))).toEqual({ email, verified: 'verified', session: true })
}

async function login(page, email, password) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expectIdentity(page, email)
}

async function freshSession(browser, testInfo, label, perform) {
  const context = await browser.newContext({ baseURL: 'https://cronos.pt' })
  let page, runtime, primaryError
  const trace = testInfo.outputPath(`${label}.zip`)
  try {
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
    page = await context.newPage()
    runtime = observeAcceptanceRuntime(page)
    await perform(page)
    expect(runtime.errors, `${label} runtime`).toEqual([])
  } catch (error) { primaryError = error } finally {
    try {
      if (page) await testInfo.attach(`${label}-browser-evidence`, {
        body: await page.screenshot({ fullPage: true, mask: [page.locator('input, textarea')] }), contentType: 'image/png',
      })
      await context.tracing.stop({ path: trace })
      await testInfo.attach(`${label}-trace`, { path: trace, contentType: 'application/zip' })
    } catch (error) { primaryError ??= error }
    try { await context.close() } catch (error) { primaryError ??= error }
    runtime?.dispose()
  }
  if (primaryError) throw primaryError
}

test('founder verifies delivered email and recovers a credential through the UI', {
  annotation: ['E2E-01/founder-registration', 'E2E-01/email-verification', 'E2E-02/new-context-login', 'E2E-03/delivered-recovery', 'E2E-03/recovered-login']
    .map(description => ({ type: 'acceptance-case', description })),
}, async ({ page, browser, provenance, deliveredMail, registerSecret }, testInfo) => {
  test.setTimeout(360_000)
  const runId = process.env.E2E_RUN_ID
  if (!/^[a-z0-9-]+$/.test(runId || '') || !process.env.E2E_RUN_REGISTRY) throw new Error('A signed campaign registry is required before registration')
  const email = `admincronos100+${runId}@gmail.com`
  const password = `Cr!9-${randomBytes(24).toString('base64url')}`
  const recoveredPassword = `Cr!9-${randomBytes(24).toString('base64url')}`
  await registerSecret(password)
  await registerSecret(recoveredPassword)
  // Clerk's production sender must be observed/configured, never inferred from development.
  const sender = process.env.E2E_GMAIL_CODE_SENDER
  if (!/^[a-z0-9._-]+@cronos\.pt$/.test(sender || '')) throw new Error('Configure the observed production code sender')
  const criteria = (after, subject) => ({ recipient: email, senders: [sender], subject, purpose: 'code', after, before: after + 120_000 })

  await page.goto('/register')
  await page.getByLabel('Nome', { exact: true }).fill('Cronos')
  await page.getByLabel('Apelido', { exact: true }).fill('Aceitação')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  const consent = page.getByRole('checkbox', { name: /poderes para a vincular/ })
  await expect(consent).not.toBeChecked()
  await consent.check()
  const registrationRequestedAt = Date.now()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  const verification = await deliveredMail('admin', criteria(registrationRequestedAt, /^\d{6} is your verification code$/))
  const codeInput = page.locator('input[autocomplete="one-time-code"]').first()
  await expect(codeInput).toBeVisible()
  await codeInput.pressSequentially(verification.code)
  await expectIdentity(page, email)
  await provenance.recordCurrentActor()

  await freshSession(browser, testInfo, 'fresh-login', loginPage => login(loginPage, email, password))
  await freshSession(browser, testInfo, 'recovery', async recoveryPage => {
    await recoveryPage.goto('/recuperar-palavra-passe')
    await recoveryPage.getByLabel('Email', { exact: true }).fill(email)
    const recoveryRequestedAt = Date.now()
    await recoveryPage.getByRole('button', { name: 'Enviar código', exact: true }).click()
    await expect(recoveryPage.getByRole('heading', { name: 'Introduza o código', exact: true })).toBeVisible()
    const recovery = await deliveredMail('admin', criteria(recoveryRequestedAt, /^\d{6} is your reset password code$/))
    await recoveryPage.getByLabel('Código de verificação', { exact: true }).fill(recovery.code)
    await recoveryPage.getByRole('button', { name: 'Verificar código', exact: true }).click()
    await recoveryPage.getByLabel('Nova palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByLabel('Confirmar palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByRole('button', { name: 'Guardar e entrar', exact: true }).click()
    await expectIdentity(recoveryPage, email)
  })
  await freshSession(browser, testInfo, 'recovered-login', loginPage => login(loginPage, email, recoveredPassword))
})
