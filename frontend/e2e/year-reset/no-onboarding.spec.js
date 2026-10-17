import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  allowApiFailure,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'
import { apiRequest } from '../utils/scheduler-fixtures.js'

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

test.describe('Year reset — no legacy onboarding', () => {
  test('preserves foundation and tutorial state without reopening onboarding', async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)

    await goTo(page, '/guide')
    await expect(page.getByTestId('guide-landing')).toBeVisible()
    await page.getByRole('button', { name: /conhecer o guia/i }).click()
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    const tutorialStorageBefore = await page.evaluate(() => Object.fromEntries(
      Object.entries(localStorage).filter(([key]) => key.startsWith('cronos:tutorial:')),
    ))

    const foundationStatusBefore = await apiRequest(page, 'GET', '/foundation/status')
    // A completed organization never reopens onboarding: the wizard route is
    // replaced by school configuration.
    await goTo(page, '/foundation')
    await expect(page).toHaveURL(/\/config(?:[?#].*)?$/)

    await goTo(page, '/config')
    await page.getByRole('button', { name: 'Recomeçar ano letivo' }).click()
    await page.getByRole('checkbox', { name: /Compreendo que os horários ativos/i }).check()
    await page.getByLabel(/digite exatamente a palavra/i).fill('Confirmo')
    await page.getByRole('button', { name: 'Confirmar reinício' }).click()
    await expect(page.getByText(/Ano letivo recomeçado/i)).toBeVisible()

    const tutorialStorageAfter = await page.evaluate(() => Object.fromEntries(
      Object.entries(localStorage).filter(([key]) => key.startsWith('cronos:tutorial:')),
    ))
    expect(tutorialStorageAfter).toEqual(tutorialStorageBefore)

    const foundationStatusAfter = await apiRequest(page, 'GET', '/foundation/status')
    expect(foundationStatusAfter).toMatchObject({
      foundation_status: foundationStatusBefore.foundation_status,
      organization_name: foundationStatusBefore.organization_name,
    })

    await goTo(page, '/foundation')
    await expect(page).toHaveURL(/\/config(?:[?#].*)?$/)

    await goTo(page, '/dashboard')
    await expect(page).not.toHaveURL(/\/onboarding/)
    await expect(page).not.toHaveURL(/\/guide/)
    await expectNoAppCrash(page)

    allowApiFailure(page, { status: 404, url: '/onboarding' })
    await goTo(page, '/onboarding')
    await expect(page).toHaveURL(/\/onboarding$/)
    await expect(page.getByText(/página não encontrada|não encontrada/i)).toBeVisible()
  })
})
