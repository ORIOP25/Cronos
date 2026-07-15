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
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Onboarding — Clerk real', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('T30: login admin vê dashboard', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')
  })

  test('T33: onboarding interrompido é retomado', async ({ page }) => {
    await goTo(page, '/onboarding')
    const heading = page.locator('h1, h2').first()
    await expect(heading).toBeVisible({ timeout: 10000 })
    await expectNoAppCrash(page)
  })
})
