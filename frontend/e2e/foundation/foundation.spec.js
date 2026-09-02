import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Foundation — canonical activation', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test('validates and activates the complete foundation snapshot', async ({ page }) => {
    await goTo(page, '/foundation')
    await expectRouteReady(page, '/foundation')
    await expect(page.getByText('1. Período do Ano Letivo')).toBeVisible()

    await page.locator('#school_start_date').fill('2025-09-15')
    await page.locator('#school_hard_end_date').fill('2026-07-31')
    await page.locator('#repair_stability_window_days').fill('1')
    await page.getByRole('button', { name: /Seguinte/i }).click()

    for (const day of [0, 1, 2, 3, 4]) {
      const checkbox = page.locator(`#day-${day}`)
      if (!await checkbox.isChecked()) await checkbox.check()
    }
    await page.getByRole('button', { name: /Seguinte/i }).click()

    await page.locator('#opening_time').fill('08:00')
    await page.locator('#closing_time').fill('18:00')
    await page.getByRole('button', { name: /Seguinte/i }).click()

    await page.locator('#slot_duration_minutes').fill('50')
    await page.getByRole('button', { name: /Seguinte/i }).click()

    await page.locator('#break_duration_minutes').fill('0')
    await page.getByRole('button', { name: /Seguinte/i }).click()

    await page.locator('#lunch_window_start').fill('12:00')
    await page.locator('#lunch_window_end').fill('14:00')
    await page.locator('#lunch_min_duration_minutes').fill('60')
    await page.getByRole('button', { name: /Seguinte/i }).click()
    await page.getByRole('button', { name: /Seguinte/i }).click()

    const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
    await expect(automaticHolidays).not.toBeChecked()
    const draftSaveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/draft') &&
      response.request().method() === 'PUT' &&
      response.status() === 200
    ))
    await automaticHolidays.check()
    await draftSaveResponse
    await page.getByRole('button', { name: /Seguinte/i }).click()

    await expect(page.getByText('9. Confirmação e Ativação da Fundação')).toBeVisible()
    const confirmation = page.getByRole('checkbox', { name: /Confirmo que revi/i })
    await expect(confirmation).not.toBeChecked()
    await expect(page.getByRole('button', { name: /^Ativar Escola$/i })).toBeDisabled()
    await confirmation.check()

    const completeResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/complete') &&
      response.request().method() === 'POST'
    ))
    await page.getByRole('button', { name: /^Ativar Escola$/i }).click()
    await expect((await completeResponse).status()).toBe(200)
    await expect(page).toHaveURL(/\/dashboard(?:[?#].*)?$/)
    await expect(page.locator('aside a[href="/dashboard"]').first()).toBeVisible()
    const settings = await page.evaluate(async () => {
      const token = await window.Clerk?.session?.getToken()
      const response = await fetch('/api/v1/school/settings/', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      return response.json()
    })
    expect(settings.automatic_holidays_enabled).toBe(true)
    await expectNoAppCrash(page)
  })
})
