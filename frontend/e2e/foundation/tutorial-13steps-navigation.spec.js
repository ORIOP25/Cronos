import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe('Tutorial — 13 passos por funcionalidade', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await expect(page.locator('main.app-main')).toBeVisible({ timeout: 30_000 })
    attachRuntimeGuards(page)
  })

  test('abre explicitamente e avança pelos 13 passos sem checkpoints de legacy', async ({ page }) => {
    test.setTimeout(120_000)
    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    await expect(page.getByTestId('tutorial-step-counter')).toHaveText('Passo 1 de 13')

    for (let stepNumber = 1; stepNumber <= 13; stepNumber += 1) {
      await expect(page.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${stepNumber} de 13`)
      if (stepNumber < 13) {
        await page.getByTestId('tutorial-advance-button').click()
      } else {
        await page.getByTestId('tutorial-advance-button').click()
      }
    }

    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()
    const savedState = await page.evaluate(() => {
      const entry = Object.entries(localStorage).find(([key]) => key.includes('cronos:tutorial:v3:'))
      return entry ? JSON.parse(entry[1]) : null
    })
    expect(savedState).toEqual(expect.objectContaining({ version: 3, status: 'COMPLETED', stepId: 'history' }))
    expect(Object.keys(savedState)).toEqual(['version', 'tutorialRunId', 'status', 'stepId'])
    await expectNoAppCrash(page)
  })

  test('permite saltar o guia de forma integral', async ({ page }) => {
    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-skip-all-button')).toBeVisible()
    await page.getByTestId('tutorial-skip-all-button').click()
    await expect(page.getByTestId('tutorial-workspace')).toHaveCount(0)
    await expectNoAppCrash(page)
  })
})
