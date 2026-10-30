import { readFile } from 'node:fs/promises'
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from '@playwright/test'
import { allowApiFailure, attachRuntimeGuards, expectRouteReady, goTo, loginAsAdminReal } from '../utils/clerk-helpers.js'
import { apiRequest, firstPublishedFutureSlot, generateAndApproveThroughUi, seedMinimalSchedulerInputs } from '../utils/scheduler-fixtures.js'

test.use({ storageState: '.auth/admin.json' })

test.beforeEach(async ({ page }) => {
  attachRuntimeGuards(page)
  await loginAsAdminReal(page)
})

test('compact imports and priorities fit mobile, tablet and desktop', async ({ page }, testInfo) => {
  await seedMinimalSchedulerInputs(page)
  await generateAndApproveThroughUi(page)
  await goTo(page, '/imports')
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(page.getByRole('heading', { name: 'Importar dados' })).toBeVisible()
    await expect(page.locator('.import-resource')).toHaveCount(8)
    await expect(page.locator('.import-resource details[open]')).toHaveCount(0)
    await expect(page.getByLabel('Selecionar ficheiros CSV')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`imports-${width}.png`), fullPage: true })
  }
  await goTo(page, '/config')
  await page.getByRole('tab', { name: 'Prioridades do horário' }).click()
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(page.getByRole('radiogroup')).toHaveCount(10)
    const selectedPriority = page.locator('.priority-levels input:checked + label').first()
    const selectedColors = await selectedPriority.evaluate((element) => {
      const style = getComputedStyle(element)
      return { border: style.borderColor, background: style.backgroundColor }
    })
    expect(selectedColors.border).toBe(selectedColors.background)
    const titleGap = await page.locator('.priority-row legend').first().evaluate((element) => {
      const range = document.createRange()
      range.selectNodeContents(element)
      return range.getBoundingClientRect().top - element.closest('fieldset').getBoundingClientRect().top
    })
    expect(titleGap).toBeGreaterThanOrEqual(16)
    const actions = page.getByRole('group', { name: 'Ações das prioridades' })
    await expect(actions).toHaveCSS('justify-content', 'flex-end')
    await expect(page.locator('.priority-row details[open]')).toHaveCount(0)
    await page.locator('.priority-row summary').first().click()
    await expect(page.locator('.priority-row details[open]')).toHaveCount(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`priorities-${width}.png`), fullPage: true })
    await page.locator('.priority-row summary').first().click()
  }
  await expect(page.locator('.priority-list')).toBeVisible()
  const accessibility = await new AxeBuilder({ page }).include('.priority-list').withTags(['wcag2a', 'wcag2aa']).analyze()
  expect(accessibility.violations).toEqual([])
  await goTo(page, '/dashboard')
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(page.getByTestId('schedule-health')).toBeVisible()
    expect(await page.getByTestId('class-progress-row').count()).toBeLessThanOrEqual(5)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`dashboard-${width}.png`), fullPage: true })
  }
})

test('priority controls retain Cronos colors while saving', async ({ page }) => {
  await goTo(page, '/config')
  await page.getByRole('tab', { name: 'Prioridades do horário' }).click()
  const radio = page.locator('.priority-levels input:not(:checked)').first()
  const label = page.locator('.priority-levels input:not(:checked) + label').first()
  const normalColor = await label.evaluate((element) => getComputedStyle(element).color)
  let pendingRoute
  const endpoint = '**/school/settings/schedule-priorities'
  await page.route(endpoint, (route) => { pendingRoute = route })
  try {
    await page.getByRole('button', { name: 'Guardar prioridades', exact: true }).click()
    await expect(radio).toBeDisabled()
    await expect(label).toHaveCSS('color', normalColor)
    await expect(label).toHaveCSS('border-color', normalColor)
  } finally {
    if (pendingRoute) await pendingRoute.continue()
    await page.unroute(endpoint)
  }
  await expect(page.getByRole('status').filter({ hasText: 'Prioridades guardadas.' })).toBeVisible()
})

test('a room creates and selects its type in context while retaining its draft', async ({ page }) => {
  const typeName = `Tipo UX ${Date.now()}`
  let createdType
  try {
    await goTo(page, '/rooms')
    await expect(page.getByRole('button', { name: 'Tipos de sala', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Nova sala', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Nome da sala', { exact: true }).fill('Sala rascunho UX')
    await dialog.getByRole('button', { name: 'Adicionar tipo de sala', exact: true }).click()
    await dialog.getByLabel('Nome do novo tipo').fill(typeName)
    const created = page.waitForResponse((response) => response.url().endsWith('/room-types/') && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Criar tipo de sala', exact: true }).click()
    const response = await created
    expect(response.status()).toBe(201)
    createdType = await response.json()
    await expect(dialog.getByLabel('Tipo de sala', { exact: true })).toHaveValue(String(createdType.id))
    await dialog.getByRole('button', { name: 'Gerir tipos existentes' }).click()
    await expect(dialog.getByRole('cell', { name: typeName, exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: 'Voltar à sala' }).click()
    await expect(dialog.getByLabel('Nome da sala', { exact: true })).toHaveValue('Sala rascunho UX')
    await expect(dialog.getByLabel('Tipo de sala', { exact: true })).toHaveValue(String(createdType.id))
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
  } finally {
    if (createdType) await apiRequest(page, 'DELETE', `/room-types/${createdType.id}`)
  }
})

test('all CSV models download actual files with feedback visible in the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 451, height: 900 })
  await goTo(page, '/imports')
  await expectRouteReady(page, '/imports')
  const filenames = ['Salas', 'DisciplinasEModulos', 'CursosETurmas', 'ProfessoresECompetencias', 'Atribuicoes']
  for (const [index, name] of filenames.entries()) {
    const button = page.getByRole('button', { name: 'Descarregar modelo' }).nth(index)
    const downloadEvent = page.waitForEvent('download')
    await button.click()
    const download = await downloadEvent
    expect(await download.failure()).toBeNull()
    expect(download.suggestedFilename()).toBe(`Cronos_${name}_Template.csv`)
    const bytes = await readFile(await download.path())
    expect([...bytes.subarray(0, 3)]).toEqual([239, 187, 191])
    expect(bytes.toString('utf8')).toContain(';')
    const feedback = page.locator('[data-rht-toaster]').getByText('Transferência iniciada. Verifique a pasta de transferências.', { exact: true }).first()
    await expect(feedback).toBeInViewport()
  }
  const bundleEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Descarregar os modelos deste passo' }).first().click()
  const bundle = await bundleEvent
  expect(await bundle.failure()).toBeNull()
  expect(bundle.suggestedFilename()).toBe('Cronos_Modelos_DadosDaEscola.zip')
  const zip = await readFile(await bundle.path())
  expect(zip.subarray(0, 2).toString('latin1')).toBe('PK')
  for (const name of filenames) expect(zip.includes(Buffer.from(`Cronos_${name}_Template.csv`))).toBe(true)
})

test('calendar action fits tablet and desktop; mobile debt cards stay inside the viewport', async ({ page }) => {
  test.setTimeout(180_000)
  allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
  await goTo(page, '/config')
  await page.getByRole('tab', { name: 'Calendário e interrupções' }).click()
  for (const width of [768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    const button = page.getByRole('button', { name: 'Adicionar evento', exact: true })
    await expect(button).toBeVisible()
    expect(await button.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  }
  const classroom = await seedMinimalSchedulerInputs(page)
  await generateAndApproveThroughUi(page)
  const lesson = await firstPublishedFutureSlot(page, classroom.id)
  expect(lesson.can_create_occurrence).toBe(true)
  await apiRequest(page, 'PUT', `/schedule/lessons/${lesson.scheduler_lesson_id}/log`, { status: 'OCCURRENCE', summary: 'QA mobile', notes: '' })
  const occurrences = await apiRequest(page, 'GET', '/occurrences/')
  const occurrence = occurrences.items.find((item) => item.class_id === classroom.id && item.date === lesson.date)
  expect(occurrence).toBeTruthy()
  const decision = await apiRequest(page, 'PATCH', `/occurrences/${occurrence.id}`, { status: 'GAP', version: occurrence.version })
  const debts = await apiRequest(page, 'GET', '/occurrences/debts')
  const dashboard = await apiRequest(page, 'GET', '/dashboard')
  expect(dashboard.debts.total_gaps).toBe(debts.total_gaps)
  expect(dashboard.debts.total_hours_owed).toBe(debts.total_hours_owed)
  await page.setViewportSize({ width: 451, height: 900 })
  await goTo(page, '/absences?tab=debts')
  const cards = page.getByRole('region', { name: 'Dívidas por turma' })
  await expect(cards).toBeVisible()
  expect(await cards.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const accessibility = await new AxeBuilder({ page }).include('[aria-label="Dívidas por turma"]').withTags(['wcag2a', 'wcag2aa']).analyze()
  expect(accessibility.violations).toEqual([])
  await apiRequest(page, 'POST', `/occurrences/${occurrence.id}/cancel`, { version: decision.version })
  const revertedDebts = await apiRequest(page, 'GET', `/occurrences/debts?class_id=${classroom.id}`)
  expect(revertedDebts.total_gaps).toBe(0)
  expect(revertedDebts.total_hours_owed).toBe(0)
})

test('the team screen exposes the school-presence rule and its CSV model without writing', async ({ page }) => {
  await goTo(page, '/members')
  await expectRouteReady(page, '/members')

  // The prepared E2E teacher is the active member with a teacher profile. The
  // button is the only way the direction reaches the presence rule, so opening
  // it against the real API is the observable journey under test.
  const teacherRow = page.getByRole('row').filter({ hasText: 'Professor' }).first()
  await teacherRow.getByRole('button', { name: 'Editar membro', exact: true }).click()
  const availabilityButton = page.getByRole('button', { name: 'Editar disponibilidade', exact: true })
  await expect(availabilityButton).toBeVisible({ timeout: 30_000 })
  await expect(availabilityButton).toHaveClass(/btn-outline-primary/)
  const memberDialog = page.getByRole('dialog')
  await expect(memberDialog.getByRole('button', { name: 'Cancelar', exact: true })).toHaveClass(/btn-outline-secondary/)
  const actionColor = await availabilityButton.evaluate((element) => getComputedStyle(element).color)
  const primaryBackground = await memberDialog.getByRole('button', { name: 'Guardar alterações', exact: true }).evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(actionColor).toBe(primaryBackground)
  const presenceRequest = page.waitForResponse((response) => (
    response.url().includes('/presence')
    && response.request().method() === 'GET'
  ))
  await availabilityButton.click()
  const presenceResponse = await presenceRequest
  expect(presenceResponse.status()).toBe(200)

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Presença na escola' })).toBeVisible()
  await expect(dialog.getByText('Vale para todas as grelhas e anos letivos.')).toBeVisible()
  await expect(dialog.getByRole('radio', { name: 'Sim', exact: true })).toBeVisible()
  await expect(dialog.getByRole('radio', { name: 'Não', exact: true })).toBeVisible()
  // The rule is enabled only after the saved value loads; the field stays
  // visible but disabled while the request is in flight or fails.
  const minimumHours = dialog.getByLabel('Mínimo de horas por presença')
  await expect(minimumHours).toBeVisible()
  await expect(minimumHours).toBeEnabled()
  await expect(dialog.getByText(/Uma presença é a manhã ou a tarde/)).toBeVisible()

  // Read-only: close without saving or editing any field.
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Disponibilidade —/ })).toBeHidden()
  await expect(page.getByRole('heading', { name: 'Editar membro' })).toBeVisible()

  await goTo(page, '/imports')
  await expect(page.getByRole('heading', { name: 'Importar dados' })).toBeVisible()
  const presenceCard = page.locator('.import-resource').filter({ hasText: 'Presença dos professores' })
  await expect(presenceCard).toBeVisible()
  await expect(presenceCard.getByRole('button', { name: 'Descarregar modelo' })).toBeVisible()
})

test('creating a course preserves the filled initial class without Add class', async ({ page }) => {
  await goTo(page, '/courses')
  await page.getByRole('button', { name: 'Novo curso' }).click()
  const dialog = page.getByRole('dialog')
  const courseName = `Curso QA ${Date.now()}`
  await dialog.getByLabel('Nome do curso', { exact: true }).fill(courseName)
  await dialog.getByLabel('Sigla', { exact: true }).fill('QAUX')
  await dialog.getByLabel('Nome Turma', { exact: true }).fill('QA UX 10')
  await dialog.getByLabel('Alunos', { exact: true }).fill('20')
  const responseEvent = page.waitForResponse((response) => response.url().endsWith('/api/v1/courses/') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'Criar curso' }).click()
  const response = await responseEvent
  expect(response.status()).toBe(200)
  const course = await response.json()
  const persisted = await apiRequest(page, 'GET', `/courses/${course.id}`)
  expect(persisted.classes).toEqual(expect.arrayContaining([expect.objectContaining({ name: 'QA UX 10', size: 20 })]))
})
