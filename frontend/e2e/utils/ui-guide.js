import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'

async function readSchoolCatalog(page) {
  return Promise.all(['rooms/', 'subjects/', 'courses/', 'school/settings/'].map(path => readSchoolResource(page, path)))
}

async function readProgress(page) {
  return page.evaluate(() => {
    const key = `cronos:tutorial:v3:user:${window.Clerk.user.id}:org:${window.Clerk.organization.id}`
    const saved = JSON.parse(localStorage.getItem(key) || 'null')
    return { key, state: saved?.value ?? saved }
  })
}

export async function completeAndResumeGuide(page, testInfo, runId) {
  const before = await readSchoolCatalog(page)
  const writes = [], telemetry = []
  const observe = request => {
    const url = new URL(request.url())
    if (url.origin !== 'https://api.cronos.pt' || !url.pathname.startsWith('/api/v1/')) return
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push({ method: request.method(), path: url.pathname })
    if (url.pathname.startsWith('/api/v1/tutorial/telemetry')) telemetry.push(url.pathname)
  }
  page.on('request', observe)
  try {
    await page.goto('/guide')
    await expect(page.getByRole('heading', { name: 'Conhecer o guia', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Conhecer o guia', exact: true }).click()
    const panel = page.getByRole('complementary', { name: 'Instruções do guia', exact: true })
    await expect(panel.getByTestId('tutorial-step-counter')).toHaveText('Passo 1 de 13')
    await expect(page.getByText('Ambiente de demonstração · os dados da escola não são alterados.', { exact: true })).toBeVisible()
    await page.locator('[data-tutorial-target="edit-record-1"]').click()
    const name = `Demonstração ${runId}`
    await page.getByLabel('Nome da Disciplina', { exact: true }).fill(name)
    await page.getByRole('button', { name: 'Guardar Disciplina', exact: true }).click()
    await expect(page.getByText('Disciplina atualizada.', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: `Editar ${name}`, exact: true })).toBeVisible()
    await panel.getByRole('button', { name: 'Continuar', exact: true }).click()
    await expect(panel.getByTestId('tutorial-step-counter')).toHaveText('Passo 2 de 13')
    const partial = await readProgress(page)
    expect(partial.state).toMatchObject({ version: 3, status: 'IN_PROGRESS', stepId: 'courses_classes' })
    expect(typeof partial.state.tutorialRunId).toBe('string')
    await panel.getByRole('button', { name: 'Sair do guia', exact: true }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await page.goto('/guide')
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Retomar o guia', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Retomar guia', exact: true }).click()
    await expect(panel.getByTestId('tutorial-step-counter')).toHaveText('Passo 2 de 13')
    expect(await readProgress(page)).toEqual(partial)
    await panel.getByRole('button', { name: '← Rever anterior', exact: true }).click()
    await expect(panel.getByText('A rever o passo 1', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: `Editar ${name}`, exact: true })).toHaveCount(0)
    await panel.getByRole('button', { name: 'Voltar ao passo atual', exact: true }).click()
    for (let step = 2; step <= 13; step += 1) {
      await expect(panel.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${step} de 13`)
      await panel.getByRole('button', { name: step === 13 ? 'Concluir guia' : 'Continuar', exact: true }).click()
    }
    await expect(page.getByRole('heading', { name: 'Guia concluído', exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Guia concluído', exact: true })).toBeVisible()
    const completed = await readProgress(page)
    expect(completed.key).toBe(partial.key)
    expect(completed.state).toEqual({ version: 3, tutorialRunId: partial.state.tutorialRunId, status: 'COMPLETED', stepId: 'history' })
    expect(await readSchoolCatalog(page)).toEqual(before)
    expect(writes, 'The guide must not mutate the real school').toEqual([])
    expect(telemetry, 'The guide must remain local').toEqual([])
    await testInfo.attach('guide-resume-completion-and-isolation', {
      body: Buffer.from(JSON.stringify({ partial, completed, writes, telemetry, catalog_unchanged: true })), contentType: 'application/json',
    })
  } finally { page.off('request', observe) }
}
