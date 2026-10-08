import { observeAcceptanceRuntime } from './acceptance-runtime.js'
import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'

export async function expectIdentity(page, email) {
  await expect.poll(() => page.evaluate(() => ({
    email: window.Clerk?.user?.primaryEmailAddress?.emailAddress,
    verified: window.Clerk?.user?.primaryEmailAddress?.verification?.status,
    session: Boolean(window.Clerk?.session),
  }))).toEqual({ email, verified: 'verified', session: true })
}

export async function login(page, email, password) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expectIdentity(page, email)
}

export async function loginPersistentActor(page, school, actor, password) {
  await login(page, actor.email, password)
  expect(await page.evaluate(() => window.Clerk.user.id)).toBe(actor.id)
  if (await page.evaluate(() => window.Clerk.organization?.id) !== school.clerk_id) {
    await page.getByRole('group', { name: 'Selecionar escola', exact: true }).getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
    await page.getByText(`Cronos Aceitação ${school.creation_run_id}`, { exact: true }).click()
  }
  await expect.poll(() => page.evaluate(() => window.Clerk.organization?.id)).toBe(school.clerk_id)
  const member = await readSchoolResource(page, 'members/me')
  expect(member.organization_id).toBe(school.local_id)
  return member
}

export async function freshSession(browser, testInfo, label, perform) {
  const context = await browser.newContext({ baseURL: 'https://cronos.pt' })
  let page, runtime, primaryError
  const trace = testInfo.outputPath(`${label}.zip`)
  try {
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
    page = await context.newPage()
    runtime = observeAcceptanceRuntime(page)
    await perform(page, runtime)
    await page.waitForLoadState('load')
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
  expect(runtime.errors, `${label} runtime`).toEqual([])
}
