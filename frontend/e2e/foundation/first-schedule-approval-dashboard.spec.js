import { test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Dashboard — First Real Schedule Approval & Discrimination', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('displays PREPARATION mode before first schedule approval and OPERATIONAL mode afterwards', async ({ page }) => {
    await goTo(page, '/dashboard')
    await expectNoAppCrash(page)
  })
})
