import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Tutorial — deterministic local scenario', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await page.evaluate(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
  })

  test('completes all 24 local transitions and persists the scenario', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-modal')).toBeVisible()
    await expect(page.getByTestId('tutorial-step-counter')).toHaveText('Passo 1 de 24')

    for (let step = 1; step < 24; step += 1) {
      await page.getByTestId('tutorial-next-button').click()
    }
    await page.getByTestId('tutorial-next-button').click()
    await expect(page.getByTestId('tutorial-modal')).toBeHidden()

    const savedState = await page.evaluate(() => {
      const entry = Object.entries(localStorage).find(([key]) => key.startsWith('cronos:tutorial:'))
      return entry ? JSON.parse(entry[1]) : null
    })
    expect(savedState.status).toBe('COMPLETED')
    expect(savedState.completed).toBe(true)
    expect(savedState.simulationData.sampleCourses).toHaveLength(2)
    expect(savedState.simulationData.sampleClasses).toHaveLength(3)
    expect(savedState.simulationData.sampleSubjects).toHaveLength(5)
    expect(savedState.simulationData.sampleTeachers).toHaveLength(4)
    expect(savedState.simulationData.sampleRooms).toHaveLength(3)
    expect(savedState.simulationData.workflow.historyPreserved).toBe(true)
    await expectNoAppCrash(page)
  })
})
