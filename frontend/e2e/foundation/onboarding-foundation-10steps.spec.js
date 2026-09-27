import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

test.describe('Foundation — 10-Step Wizard Flow', () => {
  test('reaches the summary with automatic holidays disabled and no internship flows', async ({ page }) => {
    test.setTimeout(120_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for foundation E2E.')
    const client = createClerkClient({ secretKey })
    let founder
    let primaryError = null
    let cleanupError = null
    attachRuntimeGuards(page)

    try {
      founder = await createFreshFounder(page, client, 'Foundation')
      await expectRouteReady(page, '/foundation')

      // Step 1: Period
      await expect(page.locator('text=1. Período do Ano Letivo')).toBeVisible({ timeout: 10000 })
      await page.locator('#school_start_date').fill('2025-09-15')
      await page.locator('#school_hard_end_date').fill('2026-07-31')
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 2: Days
      await expect(page.locator('text=2. Dias de Funcionamento Letivo')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 3: Opening
      await expect(page.locator('text=3. Horário de Abertura e Encerramento')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 4: Slot duration
      await expect(page.locator('text=4. Duração dos Blocos de Aulas')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 5: Break duration
      await expect(page.locator('text=5. Intervalos entre Blocos')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 6: Lunch
      await expect(page.locator('text=6. Período e Duração de Almoço')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 7: Preview
      await expect(page.locator('text=7. Pré-visualização da Grelha Horária')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /seguinte/i }).click()

      // Step 8: Calendar
      await expect(page.locator('text=8. Feriados e Pausas Letivas')).toBeVisible({ timeout: 10000 })
      const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
      await expect(automaticHolidays).not.toBeChecked()
      await page.getByRole('button', { name: /ignorar por agora/i }).click()

      // Step 9: Internship flows (optional)
      await expect(page.locator('text=9. Fluxos de Estágio (opcional)')).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: /ignorar por agora/i }).click()

      // Step 10: Summary & Activation
      await expect(page.locator('text=10. Confirmação e Ativação da Fundação')).toBeVisible({ timeout: 10000 })
      await expect(page.getByText('Feriados automáticos:').locator('..')).toContainText('Desativados')
      await expect(page.getByText('Fluxos de estágio:').locator('..')).toContainText('Nenhum')
      await expectNoAppCrash(page)
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
})
