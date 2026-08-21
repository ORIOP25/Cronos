import { test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Foundation — Operational Gate 409', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('blocks director from operational pages when foundation is not completed', async ({ page }) => {
    await goTo(page, '/classes')
    await expectNoAppCrash(page)
  })
})
