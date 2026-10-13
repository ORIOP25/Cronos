import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { recordCheckpoint } from './acceptance-proof.js'
import { campaignSchoolLabel } from './acceptance-policy.js'
import { evaluateAcrossNavigation } from './ui-auth.js'
import { validateImportedData } from './expected-results.js'
import { completeFoundation, futureSchoolPeriod, importOriginalData, readImportedData, readSchoolResource } from './ui-school.js'

async function selectSchool(page, school) {
  await page.getByRole('group', { name: 'Selecionar escola', exact: true }).getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
  await page.getByText(school.name, { exact: true }).click()
  await expect.poll(() => evaluateAcrossNavigation(page, () => window.Clerk?.organization?.id)).toBe(school.clerk_id)
  await expect(page).toHaveURL(/\/dashboard$/)
  expect((await readSchoolResource(page, 'members/me')).organization_id).toBe(school.local_id)
}

async function verifyLateDownloadFeedback(page, testInfo, first, second) {
  await page.goto('/imports')
  const cdp = await page.context().newCDPSession(page)
  let paused
  const capture = event => { paused = event }
  cdp.on('Fetch.requestPaused', capture)
  try {
    await cdp.send('Fetch.enable', { patterns: [{
      urlPattern: '*://*/api/v1/imports/templates/rooms', requestStage: 'Response', resourceType: 'XHR',
    }] })
    const downloading = page.waitForEvent('download')
    // Observe the promise even if switching fails before the download arrives.
    downloading.catch(() => {})
    await page.locator('.card').filter({ has: page.locator('#import-rooms') })
      .getByRole('button', { name: 'Descarregar modelo', exact: true }).click()
    await expect.poll(() => Boolean(paused)).toBe(true)
    expect(paused.request.method).toBe('GET')
    expect(paused.responseStatusCode).toBe(200)
    const response = await cdp.send('Fetch.getResponseBody', { requestId: paused.requestId })
    const bytes = Buffer.from(response.body, response.base64Encoded ? 'base64' : 'utf8')
    expect(bytes.length).toBeGreaterThan(0)
    await expect(page.getByText('A preparar…', { exact: true })).toBeVisible()
    await selectSchool(page, second)
    const feedback = 'Transferência iniciada. Verifique a pasta de transferências.'
    await page.evaluate(text => {
      const observation = { seen: document.body.textContent.includes(text) }
      observation.observer = new MutationObserver(() => {
        observation.seen ||= document.body.textContent.includes(text)
      })
      observation.observer.observe(document.body, { childList: true, subtree: true, characterData: true })
      window.__lateFeedbackObservation = observation
    }, feedback)
    // Continue the original response; no status, headers or body are replaced.
    await cdp.send('Fetch.continueResponse', { requestId: paused.requestId })
    const download = await downloading
    expect(await download.failure()).toBeNull()
    expect(download.suggestedFilename()).toBe('Cronos_Salas_Template.csv')
    const path = testInfo.outputPath('late-first-school-rooms-model.csv')
    await download.saveAs(path)
    expect(await readFile(path)).toEqual(bytes)
    const feedbackSeen = await page.evaluate(async () => {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      const observation = window.__lateFeedbackObservation
      observation.observer.disconnect()
      delete window.__lateFeedbackObservation
      return observation.seen
    })
    expect(feedbackSeen, 'a real response from the previous school must emit no feedback here').toBe(false)
    await expect(page.getByText(feedback, { exact: true })).toHaveCount(0)
    expect((await readSchoolResource(page, 'members/me')).organization_id).toBe(second.local_id)
    await testInfo.attach('late-response-school-feedback-isolation', {
      body: Buffer.from(JSON.stringify({ initiating_school: first, receiving_school: second,
        response_status: paused.responseStatusCode, original_response_preserved: true,
        downloaded_bytes: bytes.length, stale_feedback_seen: feedbackSeen })), contentType: 'application/json',
    })
  } finally {
    cdp.off('Fetch.requestPaused', capture)
    await cdp.send('Fetch.disable')
    await cdp.detach()
  }
  await selectSchool(page, first)
}

async function deleteDisposableSchool(page, testInfo, provenance, first, second, firstCatalog) {
  await selectSchool(page, second)
  const backup = await provenance.exportBeforeDeletion(testInfo, second)
  await page.getByRole('group', { name: 'Selecionar escola', exact: true })
    .getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
  await page.getByText('Configurar organização', { exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar organização', exact: true }).click()
  const dialog = page.getByRole('dialog').last()
  await expect(dialog.getByText('Esta ação é permanente e irreversível.', { exact: true })).toBeVisible()
  const confirm = dialog.getByRole('button', { name: 'Eliminar organização', exact: true })
  await expect(confirm).toBeDisabled()
  const field = dialog.getByRole('textbox')
  await expect(field).toHaveCount(1)
  await field.fill('nome incorreto')
  await expect(confirm).toBeDisabled()
  await field.fill(second.name)
  await expect(confirm).toBeEnabled()
  const deleted = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.origin === 'https://clerk.cronos.pt' && url.pathname.endsWith(`/organizations/${second.clerk_id}`) && response.request().method() === 'DELETE'
  })
  await confirm.click()
  const response = await deleted
  expect(response.status()).toBe(200)
  await expect.poll(async () => page.evaluate(async id => {
    const memberships = await window.Clerk.user.getOrganizationMemberships({ pageSize: 100, initialPage: 1 })
    if (memberships.total_count !== memberships.data.length) throw new Error('Post-deletion membership inventory is incomplete')
    return memberships.data.some(item => item.organization.id === id)
  }, second.clerk_id)).toBe(false)
  await page.goto('/dashboard')
  await expect.poll(() => evaluateAcrossNavigation(page, () => window.Clerk?.organization?.id)).toBe(first.clerk_id)
  expect(await readImportedData(page)).toEqual(firstCatalog)
  await page.getByRole('group', { name: 'Selecionar escola', exact: true })
    .getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
  await expect(page.getByText(second.name, { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await testInfo.attach('native-disposable-school-deletion', {
    body: Buffer.from(JSON.stringify({ deleted_school: second, retained_school: first,
      protected_backup: backup.exports, native_delete_status: response.status(),
      deleted_membership_absent: true, retained_catalog_unchanged: true })), contentType: 'application/json',
  })
}

export async function exerciseSchoolIsolation(page, testInfo, provenance, original, converted, runId) {
  const first = await page.evaluate(() => ({ name: window.Clerk.organization.name, clerk_id: window.Clerk.organization.id }))
  const firstCatalog = await readImportedData(page)
  first.local_id = firstCatalog.organization_id
  expect(validateImportedData(converted.original, firstCatalog)).toEqual(converted.identities)
  const firstSettings = await readSchoolResource(page, 'school/settings/')
  await page.getByRole('group', { name: 'Selecionar escola', exact: true }).getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
  await page.getByText('Criar organização', { exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Criar organização', exact: true })).toBeVisible()
  const secondName = `Cronos Isolamento ${campaignSchoolLabel(runId)}`
  await dialog.getByLabel('Nome da organização', { exact: true }).fill(secondName)
  // Signed write-ahead organization intent before the second Clerk school exists.
  const creationIntentId = await provenance.beginOrganizationCreation()
  await dialog.getByRole('button', { name: 'Criar organização', exact: true }).click()
  const skipInvitations = page.getByRole('button', { name: 'Ignorar', exact: true })
  const legal = page.getByRole('checkbox', { name: 'Confirmo a aceitação dos documentos legais atuais pela organização.', exact: true })
  const foundationStart = page.locator('#school_start_date')
  for (let step = 0; step < 3; step += 1) {
    await expect.poll(async () => await foundationStart.isVisible() || await skipInvitations.isVisible() || await legal.isVisible()).toBe(true)
    if (await foundationStart.isVisible()) break
    if (await skipInvitations.isVisible()) {
      await skipInvitations.click()
      await expect(skipInvitations).toBeHidden()
    }
    else {
      await legal.check()
      await page.getByRole('button', { name: 'Confirmar e continuar', exact: true }).click()
      await expect(legal).toBeHidden()
    }
  }
  await expect(foundationStart).toBeEnabled()
  await expect(page).toHaveURL(/\/foundation$/)
  await provenance.recordCreatedSchool('disposable', page, creationIntentId)
  const second = await page.evaluate(() => ({ name: window.Clerk.organization.name, clerk_id: window.Clerk.organization.id }))
  expect(second.name).toBe(secondName)
  expect(second.clerk_id).not.toBe(first.clerk_id)
  const period = futureSchoolPeriod()
  await completeFoundation(page, period, testInfo, { checkpoint: false })
  await importOriginalData(page, testInfo, { checkpoint: false })
  const secondCatalog = await readImportedData(page)
  second.local_id = secondCatalog.organization_id
  expect(second.local_id).not.toBe(first.local_id)
  const secondIdentities = validateImportedData(original, secondCatalog)
  for (const kind of Object.keys(secondIdentities)) {
    const firstIds = new Set(Object.values(converted.identities[kind]))
    expect(Object.values(secondIdentities[kind]).some(id => firstIds.has(id)), `${kind} identities must belong to different schools`).toBe(false)
  }
  const secondSettings = await readSchoolResource(page, 'school/settings/')
  expect(secondSettings.school_start_date).toBe(period.start)
  expect(secondSettings.school_start_date).not.toBe(firstSettings.school_start_date)
  await provenance.recordCreatedSchool('disposable', page)
  const originalTeacherEmail = Object.keys(original.teachers)[0]
  for (const school of [first, second, first]) {
    await selectSchool(page, school)
    const isFirst = school.local_id === first.local_id
    expect(await readImportedData(page)).toEqual(isFirst ? firstCatalog : secondCatalog)
    await page.goto('/config')
    const settings = isFirst ? firstSettings : secondSettings
    await expect(page.getByRole('heading', { name: school.name, exact: true })).toBeVisible()
    for (const [id, field] of [['startDate', 'school_start_date'], ['hardEndDate', 'school_hard_end_date'], ['preferredEndDate', 'preferred_end_date']]) {
      await expect(page.locator(`#${id}`)).toHaveValue(settings[field].split('-').reverse().join('/'))
    }
    await page.goto('/members')
    await expect(page.getByText(isFirst ? converted.member.email : originalTeacherEmail, { exact: true })).toBeVisible()
    await expect(page.getByText(isFirst ? originalTeacherEmail : converted.member.email, { exact: true })).toHaveCount(0)
    await expect(page.getByText('Importação concluída.', { exact: true })).toHaveCount(0)
  }
  await verifyLateDownloadFeedback(page, testInfo, first, second)
  await deleteDisposableSchool(page, testInfo, provenance, first, second, firstCatalog)
  await testInfo.attach('distinct-schools-and-native-switch-isolation', {
    body: Buffer.from(JSON.stringify({ first, second, firstSettings, secondSettings, resource_ids_disjoint: true,
      full_original_data_in_both_schools: true, switches: [first.local_id, second.local_id, first.local_id] })), contentType: 'application/json',
  })
  await recordCheckpoint(testInfo, [
    'E2E-14/distinct-schools', 'E2E-14/switch-without-cache-leak', 'E2E-14/stale-feedback-blocked',
    'E2E-18/disposable-school-deletion',
  ], { requires: 'school', observation: { first: first.local_id, second: second.local_id } })
}
