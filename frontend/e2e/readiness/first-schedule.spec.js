import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

test.describe('Readiness — first schedule', () => {
  test('exposes the canonical six-level chain before generation', async ({ page }) => {
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
    expect(readiness.body.depth).toBeLessThanOrEqual(6)
    expect(readiness.body.steps).toHaveLength(6)
    expect(readiness.body.steps.map((step) => step.code)).toEqual([
      'ACTIVE_CLASSES',
      'MODULES',
      'TEACHERS',
      'TEACHER_ASSIGNMENT',
      'COMPATIBLE_ROOM',
      'TEACHER_AVAILABILITY',
    ])
    expect(readiness.body.steps.map((step) => step.code)).not.toContain('CLASS_SUBJECTS')
    expect(readiness.body.steps.map((step) => step.code)).not.toContain('TIMESLOTS')

    if (readiness.body.depth === 2) {
      await expect(
        page.getByTestId('preparation-level-TEACHERS').getByRole('link', { name: /configurar/i }),
      ).toHaveAttribute('href', '/members')
    }
    await expectNoAppCrash(page)
  })
})
