import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

const isAllowedTutorialRequest = (url) => (
  url.includes('/api/v1/tutorial/telemetry')
  || url.includes('/api/v1/members/me')
)

test.describe('Tutorial — network boundary', () => {
  test('uses local simulation only and sends telemetry without operational mutations', async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await page.waitForLoadState('networkidle')
    attachRuntimeGuards(page)

    const requests = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/')) requests.push(request.url())
    })

    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()

    for (let stepNumber = 1; stepNumber <= 24; stepNumber += 1) {
      await expect(page.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${stepNumber} de 24`)
      const stepId = await page.getByTestId('tutorial-instruction-panel').getAttribute('data-step-id')
      const skipButton = page.getByTestId('tutorial-skip-step-button')
      if (await skipButton.isVisible()) await skipButton.click()
      else {
        const panelButton = page.getByTestId('tutorial-complete-step')
        if (await panelButton.isVisible()) await panelButton.click()
        else if (stepId === 'published_block_open') await page.locator('[data-tutorial-target="schedule-grid"] button:not([disabled])').first().click()
        else if (stepId === 'substitute_teacher_select') await page.getByRole('button', { name: /decidir/i }).click()
        else if (stepId === 'substitute_subject_select') await page.getByRole('button', { name: /substituída/i }).click()
        else if (stepId === 'repair_approve') await page.locator('button[data-tutorial-target="approve-schedule"]').click()
        else throw new Error(`No local completion control for mandatory tutorial step ${stepId}`)
      }

      const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
      expect(operationalRequests).toEqual([])
    }

    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()

    const operationalRequests = requests.filter((url) => !isAllowedTutorialRequest(url))
    expect(operationalRequests).toEqual([])
    await expectNoAppCrash(page)
  })
})
