import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectRouteReady,
  goTo,
} from '../utils/clerk-helpers.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

function foundationDates() {
  const start = new Date()
  start.setHours(12, 0, 0, 0)
  start.setMonth(8, 1)
  const end = new Date(start)
  end.setFullYear(start.getFullYear() + 1, 6, 31)
  const toIso = (date) => date.toISOString().slice(0, 10)
  return { start: toIso(start), end: toIso(end) }
}

async function activateFoundation(page) {
  const { start, end } = foundationDates()
  await page.locator('#school_start_date').fill(start)
  await page.locator('#school_hard_end_date').fill(end)
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
  await page.getByRole('button', { name: /Ignorar por agora/i }).click()
  await page.getByRole('button', { name: /Ignorar por agora/i }).click()
  await page.getByRole('checkbox', { name: /Confirmo que revi/i }).check()
  await page.getByRole('button', { name: /^Ativar Escola$/i }).click()
  await expect(page).toHaveURL(/\/dashboard(?:[?#].*)?$/)
}

test('saves schedule priorities for an administrator and reloads the stored level', async ({ page }) => {
  test.setTimeout(180_000)
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for schedule-priorities E2E.')
  const client = createClerkClient({ secretKey })
  let founder
  let primaryError = null
  let cleanupError = null
  attachRuntimeGuards(page)

  try {
    founder = await createFreshFounder(page, client, 'Schedule Priorities')
    await expectRouteReady(page, '/foundation')
    await activateFoundation(page)

    await goTo(page, '/config')
    await page.getByRole('tab', { name: 'Prioridades do horário' }).click()
    const classGaps = page.getByRole('radiogroup', {
      name: 'Importância: Evitar tempos livres das turmas.',
    })
    await classGaps.getByText('Muito importante', { exact: true }).click()
    await expect(classGaps.getByRole('radio', { name: 'Muito importante' })).toBeChecked()
    await page.getByRole('button', { name: 'Guardar prioridades' }).click()
    await expect(page.getByRole('status')).toContainText(
      'Prioridades guardadas. A próxima geração ou atualização usa estes valores.',
    )

    await page.reload()
    await expectRouteReady(page, '/config')
    await page.getByRole('tab', { name: 'Prioridades do horário' }).click()
    await expect(page.getByRole('radiogroup', {
      name: 'Importância: Evitar tempos livres das turmas.',
    }).getByRole('radio', { name: 'Muito importante' })).toBeChecked()
  } catch (error) {
    primaryError = error
  } finally {
    if (founder) {
      try {
        await cleanupFreshFounder(client, founder)
      } catch (error) {
        cleanupError = error
      }
    }
  }

  if (primaryError) throw primaryError
  if (cleanupError) throw cleanupError
})
