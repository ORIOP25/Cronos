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

  test.afterEach(async ({ context }) => {
    await context.unrouteAll({ behavior: 'wait' })
  })

  test('sessão persiste após page reload', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()

    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')

    await page.reload()
    await expectRouteReady(page, '/dashboard')
  })

  test('API 401 do membro mostra recuperação explícita da sessão', async ({ page }) => {
    allowApiFailure(page, { status: 401, url: '/api/v1/members/me' })
    await page.route(
      (url) => url.pathname === '/api/v1/members/me',
      (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' }),
    )
    await goTo(page, '/dashboard')
    await expect(page).toHaveURL(/\/dashboard(?:[?#].*)?$/)
    const recoveryAlert = page.getByRole('alert')
    await expect(recoveryAlert).toContainText(/sessão da organização precisa de ser atualizada/i)
    await expect(page.getByRole('button', { name: /atualizar sessão/i })).toBeVisible()
    await expect(recoveryAlert.getByRole('button', { name: /terminar sessão/i })).toBeVisible()
    await expectNoAppCrash(page)
  })

  test('API 403 na listagem de membros mostra alerta', async ({ page }) => {
    allowApiFailure(page, { status: 403, url: '/api/v1/members' })
    await page.route(
      (url) => url.pathname === '/api/v1/members',
      (route) => route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Admin access required"}' }),
    )
    await goTo(page, '/members')
    await expect(page).toHaveURL(/\/members(?:[?#].*)?$/)
    await expect(page.getByText(/Admin access required/i).first()).toBeVisible({ timeout: 10000 })
    await expectNoAppCrash(page)
  })
})
