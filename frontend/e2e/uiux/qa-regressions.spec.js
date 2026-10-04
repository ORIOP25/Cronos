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
  await apiRequest(page, 'PATCH', `/occurrences/${occurrence.id}`, { status: 'GAP', version: occurrence.version })
  await page.setViewportSize({ width: 451, height: 900 })
  await goTo(page, '/absences?tab=debts')
  const cards = page.getByRole('region', { name: 'Dívidas por turma' })
  await expect(cards).toBeVisible()
  expect(await cards.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const accessibility = await new AxeBuilder({ page }).include('[aria-label="Dívidas por turma"]').withTags(['wcag2a', 'wcag2aa']).analyze()
  expect(accessibility.violations).toEqual([])
})

test('creating a course preserves the filled initial class without Add class', async ({ page }) => {
  await goTo(page, '/courses')
  await page.getByRole('button', { name: 'Novo Curso' }).click()
  const dialog = page.getByRole('dialog')
  const courseName = `Curso QA ${Date.now()}`
  await dialog.getByLabel('Nome do Curso', { exact: true }).fill(courseName)
  await dialog.getByLabel('Sigla', { exact: true }).fill('QAUX')
  await dialog.getByLabel('Nome Turma', { exact: true }).fill('QA UX 10')
  await dialog.getByLabel('Alunos', { exact: true }).fill('20')
  const responseEvent = page.waitForResponse((response) => response.url().endsWith('/api/v1/courses/') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'Criar Curso' }).click()
  const response = await responseEvent
  expect(response.status()).toBe(200)
  const course = await response.json()
  const persisted = await apiRequest(page, 'GET', `/courses/${course.id}`)
  expect(persisted.classes).toEqual(expect.arrayContaining([expect.objectContaining({ name: 'QA UX 10', size: 20 })]))
})
