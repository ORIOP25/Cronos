import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'
import { PUBLIC_ASSET_REVISION } from '../../src/utils/publicAsset.js'

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

test.describe('Tutorial — cenário local v3', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      if (sessionStorage.getItem('cronos:e2e:tutorial-reset') === '1') return
      sessionStorage.setItem('cronos:e2e:tutorial-reset', '1')
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await expect(page.locator('main.app-main')).toBeVisible({ timeout: 30_000 })
    attachRuntimeGuards(page)
  })

  test('completa os 13 passos através do avanço do guia e guarda apenas o checkpoint mínimo', async ({ page }) => {
    test.setTimeout(120_000)
    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    await expect(page.getByTestId('tutorial-step-counter')).toHaveText('Passo 1 de 13')

    for (let stepNumber = 1; stepNumber <= 13; stepNumber += 1) {
      await expect(page.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${stepNumber} de 13`)
      await page.getByTestId('tutorial-advance-button').click()
    }

    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await expect(page.getByRole('button', { name: /repetir guia/i })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Cronos' })).toHaveAttribute('src', new RegExp(`\\/logo\\.png\\?v=${PUBLIC_ASSET_REVISION}$`))
    const savedState = await page.evaluate(() => {
      const entry = Object.entries(localStorage).find(([key]) => key.includes('cronos:tutorial:v3:'))
      const parsed = entry ? JSON.parse(entry[1]) : null
      return parsed?.value ?? parsed
    })
    expect(savedState).toEqual(expect.objectContaining({ version: 3, status: 'COMPLETED', stepId: 'history' }))
    expect(Object.keys(savedState)).toEqual(['version', 'tutorialRunId', 'status', 'stepId'])
    expect(savedState).not.toHaveProperty('chapter')
    expect(savedState).not.toHaveProperty('values')
    await expectNoAppCrash(page)
  })

  test('retoma o passo guardado depois de sair do guia', async ({ page }) => {
    await goTo(page, '/guide')
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await page.getByTestId('tutorial-advance-button').click()
    await expect(page.getByTestId('tutorial-step-counter')).toHaveText('Passo 2 de 13')
    await page.getByTestId('tutorial-exit-button').click()
    await expect(page).toHaveURL(/\/(?:dashboard|foundation)(?:[?#].*)?$/)
    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /retomar guia/i }).click()
    await expect(page.getByTestId('tutorial-step-counter')).toHaveText('Passo 2 de 13')
    await expectNoAppCrash(page)
  })
})
