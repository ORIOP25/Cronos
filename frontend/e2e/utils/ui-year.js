import { expect } from '@playwright/test'
import { validateImportedData, validateResetProtectedHistory } from './expected-results.js'
import { readMaterializedProposal } from './ui-generation.js'
import { readImportedData, readSchoolResource } from './ui-school.js'

export async function restartDisposableSchoolYear(page, testInfo, provenance, converted, organizationId, generated, operationalHistory) {
  const member = await readSchoolResource(page, 'members/me')
  expect(member.organization_id).toBe(organizationId)
  expect(member.capabilities).toContain('admin')
  // The signed producer refuses old identities, a foreign school or a persistent type.
  await provenance.recordCreatedSchool('disposable', page)
  const foundation = await readSchoolResource(page, 'foundation/status')
  expect(foundation.foundation_status).toBe('COMPLETED')
  const catalog = await readImportedData(page)
  expect(validateImportedData(converted.original, catalog)).toEqual(converted.identities)
  const published = await readSchoolResource(page, 'scheduler/status')
  expect(published).toMatchObject({ publication_state: 'PUBLISHED', active_version_id: generated.versionId, active_job: null, pending_proposal: null })
  const readHistory = () => readMaterializedProposal(page, generated.proposal.proposal_id, published.school_year,
    converted.original, { snapshot: catalog, identities: converted.identities })
  const historyBefore = await readHistory()
  validateResetProtectedHistory(historyBefore, historyBefore, operationalHistory)
  const writes = []
  const observe = request => {
    const path = new URL(request.url()).pathname
    if (request.method() === 'POST' && ['/api/v1/school/settings/soft-reset', '/api/v1/school/settings/'].includes(path)) writes.push(path)
  }
  page.on('request', observe)
  try {
    await page.goto('/config')
    await page.getByRole('button', { name: 'Recomeçar ano letivo', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText(/O histórico é conservado/)).toBeVisible()
    const confirm = dialog.getByRole('button', { name: 'Confirmar reinício', exact: true })
    await expect(confirm).toBeDisabled()
    await dialog.locator('#confirmWord').fill('confirmo')
    await dialog.getByLabel('Compreendo que os horários ativos e o progresso passam a zero.', { exact: true }).check()
    await expect(confirm).toBeDisabled()
    await dialog.locator('#confirmWord').fill('Confirmo')
    await expect(confirm).toBeEnabled()
    expect(writes).toEqual([])
    const reset = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/school/settings/soft-reset' && response.request().method() === 'POST')
    await confirm.click()
    const response = await reset
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON()).toEqual({ confirm_phrase: 'Confirmo' })
    expect(writes).toEqual(['/api/v1/school/settings/soft-reset'])
    await expect(page.getByText('Ano letivo recomeçado. Os horários deixaram de estar ativos.', { exact: true })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.reload()
    const resetStatus = await readSchoolResource(page, 'scheduler/status')
    expect(resetStatus).toMatchObject({ publication_state: 'UNPUBLISHED', active_version_id: null, active_job: null, pending_proposal: null,
      revisions: { input: 0, planning: 0, last_completed_planning: null, last_successful_generation_at: null } })
    expect(resetStatus.school_year.id).toBe(published.school_year.id)
    expect(await readSchoolResource(page, 'foundation/status')).toEqual(foundation)
    expect(await readImportedData(page)).toEqual(catalog)
    const historyAfterReset = await readHistory()
    validateResetProtectedHistory(historyBefore, historyAfterReset, operationalHistory)
    const start = Date.parse(`${published.school_year.hard_end_date}T00:00:00Z`) + 86_400_000
    const date = days => new Date(start + days * 86_400_000).toISOString().slice(0, 10)
    const period = { school_start_date: date(0), preferred_end_date: date(270), school_hard_end_date: date(365) }
    for (const [id, field] of [['startDate', 'school_start_date'], ['hardEndDate', 'school_hard_end_date'], ['preferredEndDate', 'preferred_end_date']]) {
      await page.locator(`#${id}`).fill(period[field].split('-').reverse().join('/'))
      await page.locator(`#${id}`).press('Tab')
    }
    await page.getByRole('button', { name: 'Guardar alterações', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Guardar novas datas?', exact: true })).toBeVisible()
    expect(writes).toHaveLength(1)
    const saved = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/school/settings/' && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Guardar alterações', exact: true }).click()
    const savedResponse = await saved
    expect(savedResponse.status()).toBe(200)
    expect(savedResponse.request().postDataJSON()).toMatchObject(period)
    await expect(page.getByText('Período letivo guardado.', { exact: true })).toBeVisible()
    await page.reload()
    expect(await readSchoolResource(page, 'school/settings/')).toMatchObject(period)
    const changed = await readSchoolResource(page, 'scheduler/status')
    expect(changed).toMatchObject({ publication_state: 'UNPUBLISHED', active_version_id: null,
      school_year: { start_date: period.school_start_date, preferred_end_date: period.preferred_end_date, hard_end_date: period.school_hard_end_date } })
    expect(await readSchoolResource(page, 'foundation/status')).toEqual(foundation)
    expect(await readImportedData(page)).toEqual(catalog)
    const historyAfterPeriod = await readHistory()
    const preservedLessons = validateResetProtectedHistory(historyBefore, historyAfterPeriod, operationalHistory)
    await testInfo.attach('disposable-school-protected-history-before-and-after', {
      body: Buffer.from(JSON.stringify({ organization_id: organizationId, proposal_id: generated.proposal.proposal_id,
        operationalHistory, historyBefore, historyAfterReset, historyAfterPeriod, preservedLessons })), contentType: 'application/json',
    })
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: '1. Período do Ano Letivo', exact: true })).toHaveCount(0)
    expect(writes).toEqual(['/api/v1/school/settings/soft-reset', '/api/v1/school/settings/'])
    await testInfo.attach('disposable-school-year-restart-and-period-change', {
      body: Buffer.from(JSON.stringify({ organization_id: organizationId, published, resetStatus, changed, period,
        foundation_preserved: true, original_catalog_preserved: true, writes })), contentType: 'application/json',
    })
  } finally { page.off('request', observe) }
}
