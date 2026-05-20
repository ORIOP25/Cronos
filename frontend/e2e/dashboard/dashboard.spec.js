/* global process */
/**
 * E2E Tests — Dashboard V1 Command Center
 *
 * Usa Clerk testing_tokens (cookie __session) + mock da BAPI de organizações
 * para simular um admin autenticado com org ativa.
 */
import { test, expect } from '@playwright/test'
import { loginAsAdminReal, goTo } from '../utils/clerk-helpers.js'
import { clearTokenCache } from '../utils/clerk-tokens.js'
import {
  dashboardComplete, dashboardWithAlerts, dashboardAllClear,
  dashboardEmptyOrg,
  heatmapData, timeslotsData,
} from './fixtures/dashboard-data.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockDashboardApi(page, dashboardData) {
  await page.route('**/api/v1/dashboard', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(dashboardData) })
  )
  await page.route('**/api/v1/analytics/availability-heatmap', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(heatmapData) })
  )
  await page.route('**/api/v1/import/timeslots', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(timeslotsData) })
  )
}

async function setupClerkOrg(page) {
  // Mock Clerk Frontend API para que useOrganization() retorne org:admin
  await page.route('**/clerk.accounts.dev/**/v1/organizations**', (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: [{
          object: 'organization',
          id: 'org_test_1',
          name: 'Escola Profissional de Teste',
          slug: 'escola-profissional-teste',
          members_count: 1,
          max_allowed_memberships: 100,
          admin_delete_enabled: false,
          public_metadata: {},
          created_at: Date.now(),
          updated_at: Date.now(),
        }],
      }),
    })
  })

  await page.route('**/clerk.accounts.dev/**/v1/organizations/*/memberships**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: [{
          object: 'organization_membership',
          id: 'mem_test_1',
          role: 'org:admin',
          organization: {
            object: 'organization',
            id: 'org_test_1',
            name: 'Escola Profissional de Teste',
            slug: 'escola-profissional-teste',
          },
          public_user_data: {
            user_id: 'user_test_admin',
            identifier: 'admin@escola.pt',
            first_name: 'Admin',
            last_name: 'Test',
          },
        }],
      }),
    })
  })
}

test.describe('Dashboard V1 Command Center', () => {
  test.skip(!!process.env.CI, 'Requer Docker stack completa (backend porta 8000)')

  test.beforeEach(async ({ page }) => {
    clearTokenCache()
    await loginAsAdminReal(page)
    await setupClerkOrg(page)
  })

  // -----------------------------------------------------------------------
  // Journey 1: Check-in matinal — há problemas hoje
  // -----------------------------------------------------------------------
  test('Journey 1: Director morning check-in sees alerts and navigates to resolve them', async ({ page }) => {
    await mockDashboardApi(page, dashboardWithAlerts)
    await goTo(page, '/dashboard')

    // ASSERT: AlertBar mostra as contagens corretas
    await expect(page.locator('[data-testid="alert-ocorrencias"]')).toBeVisible()
    await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('3')

    // ASSERT: Draft alert visível (pending_drafts > 0)
    await expect(page.getByText('rascunho')).toBeVisible({ timeout: 5000 })

    // ACT: Clica no card de ocorrências
    await page.locator('[data-testid="alert-ocorrencias"]').click()

    // ASSERT: Navegou para /absences
    await expect(page).toHaveURL(/\/absences/)
  })

  // -----------------------------------------------------------------------
  // Journey 2: Dia tranquilo — tudo a zero
  // -----------------------------------------------------------------------
  test('Journey 2: Director calm day — all alerts at zero, everything green', async ({ page }) => {
    await mockDashboardApi(page, dashboardAllClear)
    await goTo(page, '/dashboard')

    // ASSERT: AlertBar a zero
    await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('0')
    await expect(page.locator('[data-testid="alert-timesheets"]')).toContainText('0')
    await expect(page.locator('[data-testid="alert-substituicoes"]')).toContainText('0')

    // ASSERT: DraftAlert NOT visible when pending_drafts = 0
    await expect(page.getByText('rascunho')).not.toBeVisible()

    // ASSERT: QuickActions não visível (tudo zero — componente retorna null)
    await expect(page.locator('[data-testid="action-timesheets"]')).not.toBeVisible()
    await expect(page.locator('[data-testid="action-drafts"]')).not.toBeVisible()
  })

  // -----------------------------------------------------------------------
  // Journey 3: Turma com baixo progresso — investigar
  // -----------------------------------------------------------------------
  test('Journey 3: Director investigates low-progress class from dashboard', async ({ page }) => {
    await mockDashboardApi(page, dashboardComplete)
    await goTo(page, '/dashboard')

    // ASSERT: A primeira turma da lista tem 38% (abaixo de 50%)
    const firstClass = page.locator('[data-testid="class-progress-row"]').first()
    await expect(firstClass).toContainText('38%')
    await expect(firstClass).toBeVisible()

    // ACT: Clica na turma com baixo progresso
    await firstClass.click()

    // ASSERT: Navegou para a página de detalhe da turma
    await expect(page).toHaveURL(/\/courses\/\d+\/classes\/\d+/)
  })

  // -----------------------------------------------------------------------
  // Journey 4: Aprovar itens pendentes via QuickActions
  // -----------------------------------------------------------------------
  test('Journey 4: Director resolves pending items via QuickActions', async ({ page }) => {
    await mockDashboardApi(page, dashboardWithAlerts)
    await goTo(page, '/dashboard')

    // Wait for QuickActions to render (pending_timesheets = 5, pending_drafts = 1)
    await expect(page.locator('[data-testid="action-timesheets"]')).toBeVisible({ timeout: 5000 })

    // ACT: Clica "Aprovar timesheets (5)"
    await page.locator('[data-testid="action-timesheets"]').click()
    await page.waitForURL(/\/timesheets/, { timeout: 5000 })

    // ACT: Volta ao dashboard para testar drafts
    await goTo(page, '/dashboard')

    // ACT: Clica "Rever rascunho pendente (1)"
    await expect(page.locator('[data-testid="action-drafts"]')).toBeVisible({ timeout: 5000 })
    await page.locator('[data-testid="action-drafts"]').click()
    await page.waitForURL(/\/schedules/, { timeout: 5000 })
  })

  // -----------------------------------------------------------------------
  // Journey 5: Escola nova — sem dados
  // -----------------------------------------------------------------------
  test('Journey 5: New school — empty dashboard with helpful empty states', async ({ page }) => {
    await mockDashboardApi(page, dashboardEmptyOrg)
    await goTo(page, '/dashboard')

    // ASSERT: Contagens de recursos a 0
    await expect(page.locator('[data-testid="resource-teachers"]')).toContainText('0')
    await expect(page.locator('[data-testid="resource-classes"]')).toContainText('0')

    // ASSERT: ClassProgress mostra empty state
    await expect(page.locator('[data-testid="class-progress-empty"]')).toBeVisible()

    // ASSERT: DebtSummary mostra 0h
    await expect(page.locator('[data-testid="debt-summary"]')).toContainText('0h')

    // ASSERT: AlertBar tudo a 0
    await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('0')
  })

  // -----------------------------------------------------------------------
  // Journey 6: Layout responsivo — tablet
  // -----------------------------------------------------------------------
  test('Journey 6: Dashboard renders correctly on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 })
    await mockDashboardApi(page, dashboardComplete)
    await goTo(page, '/dashboard')

    await expect(page.locator('[data-testid="class-progress"]')).toBeVisible()
    await expect(page.locator('[data-testid="debt-summary"]')).toBeVisible()
  })
})
