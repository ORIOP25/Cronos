import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'
import {
  apiRequest,
  seedClassModuleSelectionInputs,
} from '../utils/scheduler-fixtures.js'

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

// Item 1 — Módulos por Turma. A class subject with no selected modules blocks
// generation in the prevalidation. Reselecting a module clears the blocker.
// The journey seeds its own fixtures and restores the module selection.
test.describe('Class module selection — no modules blocks generation', () => {
  test('unselecting every module blocks the prevalidation and reselecting clears it', async ({ page }) => {
    test.setTimeout(300_000)
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)

    const fixture = await seedClassModuleSelectionInputs(page)
    const subjectsPath = `/courses/${fixture.courseId}/classes/${fixture.classId}/subjects`
    const modulePath = `/classes/${fixture.classId}/subjects/${fixture.subjectId}`

    try {
      await goTo(page, subjectsPath)
      await expectRouteReady(page, subjectsPath)

      const subjectCard = page.locator('.card', { hasText: 'E2E Selection Subject' }).first()
      await subjectCard.getByRole('button', { name: /^Módulos:/ }).click()
      for (const moduleName of ['E2E Selection M1', 'E2E Selection M2']) {
        const checkbox = subjectCard.getByLabel(new RegExp(moduleName))
        await expect(checkbox).toBeChecked()
        const saved = page.waitForResponse((response) => response.url().includes(modulePath)
          && response.request().method() === 'PATCH')
        await checkbox.uncheck()
        expect((await saved).status()).toBe(200)
        await expect(checkbox).not.toBeChecked()
        await expect(checkbox).toBeEnabled()
      }

      await goTo(page, '/schedules')
      await expect(page.getByText(/sem módulos selecionados/i).first()).toBeVisible({ timeout: 30_000 })

      await goTo(page, subjectsPath)
      await subjectCard.getByRole('button', { name: /^Módulos:/ }).click()
      const firstModule = subjectCard.getByLabel(/E2E Selection M1/)
      const rechecked = page.waitForResponse((response) => response.url().includes(modulePath)
        && response.request().method() === 'PATCH')
      await firstModule.check()
      expect((await rechecked).status()).toBe(200)
      await expect(firstModule).toBeChecked()

      await goTo(page, '/schedules')
      await expect(page.getByText(/sem módulos selecionados/i)).toHaveCount(0)

      await expectNoAppCrash(page)
    } finally {
      await apiRequest(page, 'PATCH', `/classes/${fixture.classId}/subjects/${fixture.subjectId}`, {
        module_ids: fixture.moduleIds,
      })
    }
  })
})
