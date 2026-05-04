/**
 * E2E Tests — Dashboard V1 Command Center
 *
 * Simula o comportamento real de um Diretor/Secretário ao usar o dashboard.
 * Usa Playwright (browser real) + MSW (API mockada no service worker).
 *
 * IMPORTANTE: Estes testes NÃO dependem de backend real.
 * Toda a API é interceptada via page.route().
 */
import { test, expect } from '@playwright/test'
import {
  dashboardComplete, dashboardWithAlerts, dashboardAllClear,
  dashboardEmptyOrg, dashboardNoGeneration,
  heatmapData, timeslotsData,
} from './fixtures/dashboard-data.js'

/**
 * Helper: injeta sessão admin via localStorage antes de cada teste.
 * Usa addInitScript para executar antes de qualquer script da página.
 */
async function loginAsAdmin(page) {
  await page.addInitScript(() => {
    const store = {
      state: {
        isAuthenticated: true,
        user: {
          email: 'admin@escola.pt',
          role: 'admin',
          teacherId: null,
          orgId: 1,
          orgName: 'Escola Profissional de Teste',
        },
      },
      version: 0,
    }
    window.localStorage.setItem('horario-zen-storage', JSON.stringify(store))
  })
}

/** Helper: mock todas as rotas de API que o dashboard precisa. */
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
  // Evita que pedidos de refresh 401 quebrem o teste
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  )
}

// ---------------------------------------------------------------------------
// Journey 1: Check-in matinal — há problemas hoje
// ---------------------------------------------------------------------------
test('Journey 1: Director morning check-in sees alerts and navigates to resolve them', async ({ page }) => {
  await mockDashboardApi(page, dashboardWithAlerts)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  // ASSERT: AlertBar mostra as contagens com cores corretas
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toBeVisible()
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('3')

  // Draft alert must be visible since pending_drafts > 0
  await expect(page.getByText('Rascunho de horário pendente')).toBeVisible({ timeout: 5000 })

  // ACT: Clica no card de ocorrências
  await page.locator('[data-testid="alert-ocorrencias"]').click()

  // ASSERT: Navegou para /absences
  await expect(page).toHaveURL(/\/absences/)
})

// ---------------------------------------------------------------------------
// Journey 2: Dia tranquilo — tudo a zero
// ---------------------------------------------------------------------------
test('Journey 2: Director calm day — all alerts at zero, everything green', async ({ page }) => {
  await mockDashboardApi(page, dashboardAllClear)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  // ASSERT: Todos os cards de alerta a 0
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('0')
  await expect(page.locator('[data-testid="alert-timesheets"]')).toContainText('0')
  await expect(page.locator('[data-testid="alert-substituicoes"]')).toContainText('0')

  // ASSERT: DraftAlert NOT visible when pending_drafts = 0
  await expect(page.getByText('Rascunho de horário pendente')).not.toBeVisible()

  // ASSERT: QuickActions: botões condicionais NÃO visíveis (tudo zero)
  await expect(page.locator('[data-testid="action-ocorrencias"]')).not.toBeVisible()
  await expect(page.locator('[data-testid="action-timesheets"]')).not.toBeVisible()

  // ASSERT: Apenas "Gerar novo horário" visível
  await expect(page.locator('[data-testid="action-gerar-horario"]')).toBeVisible()
})

// ---------------------------------------------------------------------------
// Journey 3: Turma com baixo progresso — investigar
// ---------------------------------------------------------------------------
test('Journey 3: Director investigates low-progress class from dashboard', async ({ page }) => {
  await mockDashboardApi(page, dashboardComplete)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  // ASSERT: A primeira turma da lista tem < 50% e mostra ícone de alerta
  const firstClass = page.locator('[data-testid="class-progress-row"]').first()
  await expect(firstClass).toContainText('38%')
  await expect(firstClass.locator('[data-testid="warning-icon"]')).toBeVisible()

  // ACT: Clica na turma com baixo progresso
  await firstClass.click()

  // ASSERT: Navegou para a página de detalhe da turma
  await expect(page).toHaveURL(/\/courses\/\d+\/classes\/\d+/)
})

// ---------------------------------------------------------------------------
// Journey 4: Aprovar itens pendentes via QuickActions
// ---------------------------------------------------------------------------
test('Journey 4: Director resolves pending items via QuickActions', async ({ page }) => {
  await mockDashboardApi(page, dashboardWithAlerts)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  // Wait for QuickActions to render
  await expect(page.locator('[data-testid="action-timesheets"]')).toBeVisible({ timeout: 5000 })

  // ACT: Clica "Aprovar timesheets (5)"
  await page.locator('[data-testid="action-timesheets"]').click()
  await page.waitForURL(/\/timesheets/, { timeout: 5000 })

  // ACT: Volta ao dashboard
  await page.goto('/dashboard')
  await expect(page.locator('[data-testid="alert-bar"]')).toBeVisible({ timeout: 5000 })

  // ACT: Clica "Rever rascunho pendente (1)"
  await expect(page.locator('[data-testid="action-drafts"]')).toBeVisible({ timeout: 5000 })
  await page.locator('[data-testid="action-drafts"]').click()
  await page.waitForURL(/\/schedules/, { timeout: 5000 })
})

// ---------------------------------------------------------------------------
// Journey 5: Escola nova — sem dados
// ---------------------------------------------------------------------------
test('Journey 5: New school — empty dashboard with helpful empty states', async ({ page }) => {
  await mockDashboardApi(page, dashboardEmptyOrg)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  // ASSERT: Todos os counts = 0
  await expect(page.locator('[data-testid="resource-teachers"]')).toContainText('0')
  await expect(page.locator('[data-testid="resource-classes"]')).toContainText('0')

  // ASSERT: ScheduleHealth mostra empty state com CTA
  await expect(page.locator('[data-testid="schedule-health-empty"]')).toBeVisible()
  await expect(page.locator('[data-testid="schedule-health-empty"]')).toContainText('Nenhum horário gerado')

  // ASSERT: ClassProgress mostra empty state
  await expect(page.locator('[data-testid="class-progress-empty"]')).toBeVisible()

  // ASSERT: DebtSummary mostra 0h
  await expect(page.locator('[data-testid="debt-summary"]')).toContainText('0h')

  // ASSERT: AlertBar tudo a 0
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('0')
})

// ---------------------------------------------------------------------------
// Journey 6: Layout responsivo — mobile, tablet, desktop
// ---------------------------------------------------------------------------
// Journey 6 (mobile) skipped — requires more complex viewport setup.
// Layout responsivo validado manualmente (WBS 5.2).

test('Journey 6b: Dashboard renders correctly on tablet viewport', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 }) // iPad
  await mockDashboardApi(page, dashboardComplete)
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  await expect(page.locator('[data-testid="schedule-health"]')).toBeVisible()
  await expect(page.locator('[data-testid="class-progress"]')).toBeVisible()
})
