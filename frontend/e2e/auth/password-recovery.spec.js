import { test, expect } from '@playwright/test'
import { attachRuntimeGuards, expectNoAppCrash, goTo } from '../utils/clerk-helpers.js'

test('login exposes a working recovery path for an existing account', async ({ page }) => {
  attachRuntimeGuards(page)
  await goTo(page, '/login')

  const recoveryLink = page.getByRole('link', { name: /recuperar palavra-passe/i })
  await expect(recoveryLink).toBeVisible()
  await recoveryLink.click()

  await expect(page).toHaveURL(/\/recuperar-palavra-passe$/)
  await expect(page.getByRole('heading', { name: /recuperar palavra-passe/i })).toBeVisible()
  await expect(page.getByText(/entrar com google/i)).toBeVisible()

  const recoveryEmail = process.env.E2E_CLERK_TEACHER_EMAIL
  expect(recoveryEmail).toMatch(/\+clerk_test@example\.com$/)
  await page.getByRole('textbox', { name: /email/i }).fill(recoveryEmail)
  await page.getByRole('button', { name: /enviar código/i }).click()

  await expect(page.getByRole('heading', { name: /introduza o código/i })).toBeVisible()
  await expect(page.getByText(/aceitou o pedido/i)).toBeVisible()
  await expectNoAppCrash(page)
})
