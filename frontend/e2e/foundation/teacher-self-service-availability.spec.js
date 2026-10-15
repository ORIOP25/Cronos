import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'

test.describe('Teacher Self-Service — Availability Painting', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsTeacherReal(page)
  })

  test('loads availability matrix with neutral default and allows painting preferences', async ({ page }) => {
    await goTo(page, '/my-availability')
    await expectRouteReady(page, '/my-availability')

    // 1. Availability grid and toolbar are rendered
    await expect(page.getByRole('toolbar', { name: /ferramentas de disponibilidade/i })).toBeVisible()
    const grid = page.locator('.availability-grid')
    await expect(grid).toBeVisible()

    // 2. Select a preference different from the persisted value.
    const cells = page.locator('button[data-timeslot-id]')
    await expect(cells).not.toHaveCount(0)
    const firstCell = cells.first()
    const originalLabel = await firstCell.getAttribute('aria-label')
    const originalPreference = originalLabel?.match(/estado guardado: ([^,]+)/i)?.[1]
    expect(originalPreference).toBeTruthy()
    const preferenceNames = ['Preferencial', 'Neutro', 'Evitar', 'Impossível']
    const changedPreference = preferenceNames.find((name) => name !== originalPreference)
    expect(changedPreference).toBeTruthy()
    await page.getByRole('button', { name: new RegExp(`^${changedPreference}$`, 'i') }).click()

    // 3. Paint, save, reload, and verify the persisted value.
    await firstCell.click()
    await expect(page.locator('.availability-toolbar__status')).toContainText(/1 bloco alterado/i)
    const saveButton = page.getByRole('button', { name: /guardar disponibilidade/i })
    await expect(saveButton).toBeEnabled()
    const saveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/teachers/me/availability') &&
      response.request().method() === 'PUT' &&
      response.status() === 200
    ))
    await saveButton.click()
    await saveResponse
    await expect(page.locator('.availability-toolbar__status')).toContainText(/0 blocos alterados/i)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await expectRouteReady(page, '/my-availability')
    await expect(cells.first()).toHaveAttribute('aria-label', new RegExp(`estado guardado: ${changedPreference}`, 'i'))

    // Restore the shared E2E teacher fixture for the next test.
    await page.getByRole('button', { name: new RegExp(`^${originalPreference}$`, 'i') }).click()
    await cells.first().click()
    const restoreResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/teachers/me/availability') &&
      response.request().method() === 'PUT' &&
      response.status() === 200
    ))
    await saveButton.click()
    await restoreResponse

    await expectNoAppCrash(page)
  })
})
