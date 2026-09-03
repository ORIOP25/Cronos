import { clerkSetup } from '@clerk/testing/playwright'
import { expect, test as setup } from '@playwright/test'
import { loginAsAdminReal } from './utils/clerk-helpers.js'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

async function prepareDefaultOrganization(page) {
  const organizationId = process.env.E2E_CLERK_ORG_ID
  if (!organizationId) return

  await loginAsAdminReal(page)
  await page.waitForFunction(
    (id) => window.Clerk?.organization?.id === id,
    organizationId,
    { timeout: 30_000 },
  )
  await page.goto(`${BASE_URL}/foundation`, { waitUntil: 'domcontentloaded' })

  // The shared CI organization is the baseline for the legacy E2E suite. Keep
  // its foundation complete so operational routes exercise their real gate.
  if (/\/dashboard(?:[?#]|$)/.test(page.url())) return
  await page.waitForURL('**/foundation', { timeout: 30_000 })
  await expect(page.locator('#school_start_date')).toBeEnabled({ timeout: 30_000 })
  await page.locator('#school_start_date').fill('2025-09-15')
  await page.locator('#school_hard_end_date').fill('2026-07-31')
  for (let step = 1; step < 8; step += 1) {
    await page.getByRole('button', { name: /seguinte/i }).click()
  }
  const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
  if (!await automaticHolidays.isChecked()) {
    const draftSaveResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/foundation/draft')
      && response.request().method() === 'PUT'
      && response.status() === 200
    ))
    await automaticHolidays.check()
    await draftSaveResponse
  }
  await page.getByRole('button', { name: /seguinte/i }).click()
  const confirmation = page.getByRole('checkbox', { name: /confirmo que revi/i })
  if (!await confirmation.isChecked()) await confirmation.check()
  await page.getByRole('button', { name: /^ativar escola$/i }).click()
  await page.waitForURL(/\/dashboard(?:[?#].*)?$/, { timeout: 30_000 })
}

setup.describe.configure({ mode: 'serial' })

setup('configure Clerk testing token', async ({ page }) => {
  process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
  await clerkSetup()
  await page.goto('/')
  await page.waitForFunction(() => window.Clerk?.loaded)
  await prepareDefaultOrganization(page)
})
