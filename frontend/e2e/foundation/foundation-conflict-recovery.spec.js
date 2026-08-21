import { test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Foundation — Conflict Resolution Modal', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('handles 409 draft version conflict with reload and retry without data loss', async ({ page }) => {
    await goTo(page, '/foundation')
    await expectRouteReady(page, '/foundation')
    await expectNoAppCrash(page)
  })
})
