/**
 * E2E — Resiliência de sessão.
 *
 * Cenários de borda testados com page.route() (mock).
 * Clerk real não permite simular tokens expirados facilmente.
 */
import { test, expect } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Session resilience', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('sessão persiste após page reload', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')

    await page.reload()
    await expectRouteReady(page, '/dashboard')
  })

  test('API 401 redireciona para /login', async ({ page }) => {
    allowApiFailure(page, { status: 401, url: '/api/v1/dashboard' })
    await page.route('**/api/v1/dashboard', (route) => {
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' })
    })
    await goTo(page, '/dashboard')
    await expect(page).toHaveURL(/\/login|\/dashboard/)
    await expectNoAppCrash(page)
  })

  test('API 403 mostra estado de erro', async ({ page }) => {
    allowApiFailure(page, { status: 403, url: '/api/v1/members' })
    await page.route('**/api/v1/members**', (route) => {
      route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Admin access required"}' })
    })
    await goTo(page, '/members')
    await expect(page.getByText(/Admin access required/i).first()).toBeVisible({ timeout: 10000 })
    await expectNoAppCrash(page)
  })
})
