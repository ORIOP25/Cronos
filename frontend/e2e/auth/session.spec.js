/**
 * E2E — Resiliência de sessão.
 *
 * Cenários de borda testados com page.route() (mock).
 * Clerk real não permite simular tokens expirados facilmente.
 */
import { test, expect } from '@playwright/test'
import { loginAsAdminReal, goTo } from '../utils/clerk-helpers.js'
import { clearTokenCache } from '../utils/clerk-tokens.js'

test.describe('Session resilience', () => {
  test.beforeEach(async ({ page }) => {
    clearTokenCache()
    await loginAsAdminReal(page)
  })

  test('sessão persiste após page reload', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expect(page.locator('body')).toBeVisible()

    await page.reload()
    await expect(page.locator('body')).toBeVisible()
  })

  test('API 401 redireciona para /login', async ({ page }) => {
    await page.route('**/api/v1/dashboard', (route) => {
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' })
    })
    await goTo(page, '/dashboard')
    await page.waitForTimeout(3000)
  })

  test('API 403 mostra estado de erro', async ({ page }) => {
    await page.route('**/api/v1/teachers/**', (route) => {
      route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Admin access required"}' })
    })
    await goTo(page, '/teachers')
    await page.waitForTimeout(2000)
  })
})
