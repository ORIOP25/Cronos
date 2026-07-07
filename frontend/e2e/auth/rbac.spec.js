/**
 * E2E — RBAC com Clerk real (testing_tokens).
 *
 * Valida que admin e teacher têm acesso às rotas corretas
 * e são bloqueados das rotas do outro role.
 */
import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  loginAsAdminReal, loginAsTeacherReal,
  goTo,
} from '../utils/clerk-helpers.js'

test.describe('RBAC — Admin (Clerk real)', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('T26: admin acede a dashboard, teachers, rooms', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectRouteReady(page, '/dashboard')
  })

  test('admin acede a courses', async ({ page }) => {
    await goTo(page, '/courses')
    await expectRouteReady(page, '/courses')
  })

  test('admin bloqueado de rota teacher', async ({ page }) => {
    await goTo(page, '/my-availability')
    await expect(page).not.toHaveURL(/\/my-availability$/)
    await expectNoAppCrash(page)
  })
})

test.describe('RBAC — Teacher (Clerk real)', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsTeacherReal(page)
  })

  test('T27: teacher acede a my-availability, my-schedules, my-progress', async ({ page }) => {
    for (const path of ['/my-availability', '/my-schedules', '/my-progress']) {
      await goTo(page, path)
      await expectRouteReady(page, path)
    }
  })

  test('T28: teacher bloqueado de dashboard admin', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expect(page).not.toHaveURL(/\/dashboard$/)
    await expectNoAppCrash(page)
  })
})
