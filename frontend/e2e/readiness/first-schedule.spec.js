import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Readiness — first schedule', () => {
  test('exposes the canonical seven-level chain before generation', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await goTo(page, '/dashboard')

    const readiness = await page.evaluate(async () => {
      const token = await window.Clerk?.session?.getToken()
      const response = await fetch('/api/v1/readiness/bases', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      return { status: response.status, body: await response.json() }
    })

    expect(readiness.status).toBe(200)
    expect(readiness.body.depth).toBeGreaterThanOrEqual(0)
    expect(readiness.body.depth).toBeLessThanOrEqual(7)
    expect(readiness.body.steps).toHaveLength(7)
    expect(readiness.body.steps.map((step) => step.code)).toEqual([
      'ACTIVE_CLASSES',
      'MODULES',
      'CLASS_SUBJECTS',
      'TEACHER_ASSIGNMENT',
      'COMPATIBLE_ROOM',
      'TIMESLOTS',
      'TEACHER_AVAILABILITY',
    ])
    await expectNoAppCrash(page)
  })
})
