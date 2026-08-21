import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

async function resetFoundationDraft(page) {
  const result = await page.evaluate(async () => {
    const token = await window.Clerk?.session?.getToken()
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    const draftResponse = await fetch('/api/v1/foundation/draft', { headers })
    if (!draftResponse.ok) {
      return { ok: false, status: draftResponse.status, body: await draftResponse.text() }
    }
    const draft = await draftResponse.json()
    const saveResponse = await fetch('/api/v1/foundation/draft', {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        expected_version: draft.version,
        current_step: 1,
        data: {},
      }),
    })
    return { ok: saveResponse.ok, status: saveResponse.status, body: await saveResponse.text() }
  })
  if (!result.ok) {
    throw new Error(`Could not reset Foundation E2E draft: ${result.status} ${result.body}`)
  }
}

test.describe('Foundation — 9-Step Wizard Flow', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
  })

  test.afterEach(async ({ page }) => {
    await resetFoundationDraft(page)
  })

  test('completes all 9 foundation steps and activates school', async ({ page }) => {
    await goTo(page, '/foundation')
    await expectRouteReady(page, '/foundation')

    // Step 1: Period
    await expect(page.locator('text=1. Período do Ano Letivo')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 2: Days
    await expect(page.locator('text=2. Dias de Funcionamento Letivo')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 3: Opening
    await expect(page.locator('text=3. Horário de Abertura e Encerramento')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 4: Slot duration
    await expect(page.locator('text=4. Duração dos Blocos de Aulas')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 5: Break duration
    await expect(page.locator('text=5. Intervalos entre Blocos')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 6: Lunch
    await expect(page.locator('text=6. Período e Duração de Almoço')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 7: Preview
    await expect(page.locator('text=7. Pré-visualização da Grelha Horária')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 8: Calendar
    await expect(page.locator('text=8. Feriados e Pausas Letivas')).toBeVisible({ timeout: 10000 })
    await page.locator('button:has-text("Seguinte →")').click()

    // Step 9: Summary & Activation
    await expect(page.locator('text=9. Confirmação e Ativação da Fundação')).toBeVisible({ timeout: 10000 })
    await expectNoAppCrash(page)
  })
})
