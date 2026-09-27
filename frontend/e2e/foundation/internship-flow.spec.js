import { createClerkClient } from '@clerk/backend'
import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
} from '../utils/clerk-helpers.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

test.describe('Fluxos de estágio — criação manual', () => {
  test('cria um fluxo sem turmas em /config e mostra-o na lista', async ({ page }) => {
    test.setTimeout(180_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for foundation E2E.')
    const client = createClerkClient({ secretKey })
    let founder
    let primaryError = null
    let cleanupError = null
    attachRuntimeGuards(page)

    try {
      founder = await createFreshFounder(page, client, 'Internship Flow')
      await expectRouteReady(page, '/foundation')

      await page.locator('#school_start_date').fill('2025-09-15')
      await page.locator('#school_hard_end_date').fill('2026-07-31')
      await page.getByRole('button', { name: /Seguinte/i }).click()
      for (let step = 2; step < 9; step += 1) {
        await page.getByRole('button', { name: /seguinte|ignorar/i }).click()
      }
      await expect(page.locator('text=9. Fluxos de Estágio (opcional)')).toBeVisible({
        timeout: 10000,
      })
      await page.getByRole('button', { name: /ignorar por agora/i }).click()
      await expect(page.locator('text=10. Confirmação e Ativação da Fundação')).toBeVisible({
        timeout: 10000,
      })
      await page.getByRole('checkbox', { name: /Confirmo que revi/i }).check()
      await page.getByRole('button', { name: /^Ativar Escola$/i }).click()
      await expectRouteReady(page, '/dashboard')

      await goTo(page, '/config')
      await page.getByRole('tab', { name: /calendário/i }).click()
      await page.getByLabel('Tipo').selectOption('internship_flow')
      await page.getByLabel('Nome do evento').fill('Estágio 10A')
      await page.locator('#eventStart').fill('02/02/2026')
      await page.locator('#eventEnd').fill('13/02/2026')

      const createResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/school/calendar-events/') &&
        response.request().method() === 'POST'
      ))
      await page.getByRole('button', { name: /pré-visualizar e guardar/i }).click()

      expect((await createResponse).status()).toBe(200)
      await expect(page.getByText(/fluxo de estágio criado com sucesso/i)).toBeVisible()
      await expect(page.getByRole('cell', { name: 'Estágio 10A', exact: true })).toBeVisible()
      await expect(page.getByText('Sem turmas', { exact: true })).toBeVisible()
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
