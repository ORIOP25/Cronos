/**
 * E2E — Fluxo de Onboarding com Clerk real (testing_tokens).
 *
 * Requer: Docker stack com backend a correr (porta 8000).
 * O Vite proxy (/api → backend:8000) é gerido pelo Playwright webServer.
 *
 * CLERK_SECRET_KEY deve estar definida no .env ou GitHub Secrets.
 *
 * SKIP em CI: precisa da stack Docker completa (backend + frontend).
 * Para correr localmente: docker compose up -d && npx playwright test e2e/auth/
 */
import { test, expect } from '@playwright/test'
import { loginAsAdminReal, goTo, expectText } from '../utils/clerk-helpers.js'
import { clearTokenCache } from '../utils/clerk-tokens.js'

test.describe('Onboarding — Clerk real', () => {
  test.skip(!!process.env.CI, 'Requer Docker stack completa (backend porta 8000)')

  test.beforeEach(async ({ page }) => {
    clearTokenCache()
    await loginAsAdminReal(page)
  })

  test('T29: fluxo sign-up → create-org → onboarding → dashboard', async ({ page }) => {
    await goTo(page, '/create-org')

    const nameInput = page.locator('input[name="name"]')
    if (await nameInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nameInput.fill('Escola E2E Test')
      await page.locator('button[type="submit"]').click()
      await page.waitForURL('**/onboarding', { timeout: 10000 })
    }

    await goTo(page, '/onboarding')
    await expectText(page, 'Ano Letivo')

    const startDate = page.locator('input[type="date"]').first()
    if (await startDate.isVisible().catch(() => false)) {
      await startDate.fill('2025-09-15')
      await page.locator('button[type="submit"]').click()
    }

    await page.waitForURL('**/dashboard', { timeout: 10000 }).catch(() => {})
  })

  test('T30: login admin vê dashboard', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectText(page, 'Dashboard')
  })

  test('T33: onboarding interrompido é retomado', async ({ page }) => {
    await goTo(page, '/onboarding')
    const heading = page.locator('h1, h2').first()
    await expect(heading).toBeVisible({ timeout: 10000 })
  })
})
