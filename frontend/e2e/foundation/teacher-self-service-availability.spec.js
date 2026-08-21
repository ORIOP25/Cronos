import { test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Teacher Self-Service — Availability Painting', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('loads availability matrix with neutral default and allows painting preferences', async ({ page }) => {
    await goTo(page, '/my-availability')
    await expectNoAppCrash(page)
  })
})
