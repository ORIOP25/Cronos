import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Year reset — no legacy onboarding', () => {
  test('preserves foundation and tutorial state without reopening onboarding', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)

    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    const tutorialStorageBefore = await page.evaluate(() => Object.fromEntries(
      Object.entries(localStorage).filter(([key]) => key.startsWith('cronos:tutorial:')),
    ))

    const foundationStatusBeforeResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/status')
      && response.request().method() === 'GET'
    ))
    await goTo(page, '/foundation')
    const foundationStatusBefore = await (await foundationStatusBeforeResponse).json()

    await goTo(page, '/config')
    await page.getByRole('button', { name: 'Recomeçar ano letivo' }).click()
    await page.getByRole('checkbox', { name: /Compreendo que irei apagar/i }).check()
    await page.getByLabel(/digite exatamente a palavra/i).fill('Confirmo')
    await page.getByRole('button', { name: 'Remover dados e recomeçar' }).click()
    await expect(page.getByText(/Ano letivo recomeçado com sucesso/i)).toBeVisible()

    const tutorialStorageAfter = await page.evaluate(() => Object.fromEntries(
      Object.entries(localStorage).filter(([key]) => key.startsWith('cronos:tutorial:')),
    ))
    expect(tutorialStorageAfter).toEqual(tutorialStorageBefore)

    const foundationStatusAfterResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/status')
      && response.request().method() === 'GET'
    ))
    await goTo(page, '/foundation')
    const foundationStatusAfter = await (await foundationStatusAfterResponse).json()
    expect(foundationStatusAfter).toMatchObject({
      foundation_status: foundationStatusBefore.foundation_status,
      organization_name: foundationStatusBefore.organization_name,
    })

    await goTo(page, '/dashboard')
    await expect(page).not.toHaveURL(/\/onboarding/)
    await expect(page).not.toHaveURL(/\/guide/)
    await expectNoAppCrash(page)

    await goTo(page, '/onboarding')
    await expect(page).toHaveURL(/\/onboarding$/)
    await expect(page.getByText(/página não encontrada|não encontrada/i)).toBeVisible()
  })
})
