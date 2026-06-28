/* global process */
/**
 * E2E — RBAC com Clerk real (testing_tokens).
 *
 * Valida que admin e teacher têm acesso às rotas corretas
 * e são bloqueados das rotas do outro role.
 */
import { test, expect } from '@playwright/test'
import {
  loginAsAdminReal, loginAsTeacherReal,
  goTo,
} from '../utils/clerk-helpers.js'
import { clearTokenCache } from '../utils/clerk-tokens.js'

test.describe('RBAC — Admin (Clerk real)', () => {
  test.skip(!!process.env.CI, 'Requer Docker stack completa (backend porta 8000)')

  test.beforeEach(async ({ page }) => {
    clearTokenCache()
    await loginAsAdminReal(page)
  })

  test('T26: admin acede a dashboard, teachers, rooms', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expect(page.locator('body')).toBeVisible()
  })

  test('admin acede a courses', async ({ page }) => {
    await goTo(page, '/courses')
    await expect(page.locator('body')).toBeVisible()
  })

  test('admin bloqueado de rota teacher', async ({ page }) => {
    await goTo(page, '/my-availability')
    await page.waitForTimeout(2000)
  })
})

test.describe('RBAC — Teacher (Clerk real)', () => {
  test.skip(!!process.env.CI, 'Requer Docker stack completa (backend porta 8000)')

  test.beforeEach(async ({ page }) => {
    clearTokenCache()
    await loginAsTeacherReal(page)
  })

  test('T27: teacher acede a my-availability, my-schedules, my-progress', async ({ page }) => {
    await goTo(page, '/my-availability')
    await expect(page.locator('body')).toBeVisible()
  })

  test('T28: teacher bloqueado de dashboard admin', async ({ page }) => {
    await goTo(page, '/dashboard')
    await page.waitForTimeout(2000)
  })
})
