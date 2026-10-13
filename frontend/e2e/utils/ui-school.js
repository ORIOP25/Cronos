import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { isDeepStrictEqual, promisify } from 'node:util'
import { expect } from '@playwright/test'
import { recordCheckpoint } from './acceptance-proof.js'
import { validateImportedData } from './expected-results.js'
import { awaitClerkLoaded } from './ui-auth.js'

export async function readOriginalExpectations() {
  const { stdout } = await promisify(execFile)(process.env.E2E_PYTHON || 'python', [
    fileURLToPath(new URL('../../../scripts/inspect-e2e-data.py', import.meta.url)),
  ], { windowsHide: true, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } })
  return JSON.parse(stdout)
}

export async function readSchoolResource(page, path) {
  // A read right after a navigation must wait for Clerk's session to load.
  await awaitClerkLoaded(page)
  return page.evaluate(async relativePath => {
    // Production serves the API from its own origin, not from the Pages site.
    const response = await fetch(`https://api.cronos.pt/api/v1/${relativePath}`, {
      method: 'GET', redirect: 'error', headers: { Authorization: `Bearer ${await window.Clerk.session.getToken()}` },
    })
    if (!response.ok) throw new Error(`Read-only school verification failed: HTTP ${response.status}`)
    return response.json()
  }, path)
}

export async function readImportedData(page) {
  const member = await readSchoolResource(page, 'members/me')
  const kinds = ['rooms', 'subjects', 'teachers', 'courses', 'classes']
  const values = await Promise.all(kinds.map(kind => readSchoolResource(page, kind === 'courses' ? 'courses/?skip=0&limit=1000' : `${kind}/`)))
  const snapshot = { organization_id: member.organization_id, ...Object.fromEntries(kinds.map((kind, i) => [kind, values[i]])), classSubjects: [] }
  if (!Array.isArray(snapshot.classes) || snapshot.classes.some(row => !Number.isSafeInteger(row.id) || row.id <= 0)) throw new Error('Invalid class identities during read-only verification')
  for (let offset = 0; offset < snapshot.classes.length; offset += 6) {
    snapshot.classSubjects.push(...await Promise.all(snapshot.classes.slice(offset, offset + 6).map(row => readSchoolResource(page, `classes/${row.id}/subjects`))))
  }
  return snapshot
}

export async function verifyImportedData(page, original, testInfo) {
  const snapshot = await readImportedData(page)
  const identities = validateImportedData(original, snapshot)
  for (const kind of ['rooms', 'subjects', 'courses']) {
    await page.goto(`/${kind}`)
    await expect(page.locator('tbody tr')).toHaveCount(original.counts[kind])
  }
  for (const group of snapshot.classSubjects) {
    const schoolClass = snapshot.classes.find(row => row.id === group.class_id)
    await page.goto(`/courses/${schoolClass.course_id}/classes/${schoolClass.id}/subjects`)
    await expect(page.getByRole('heading', { name: schoolClass.name, exact: true })).toBeVisible()
    await expect(page.getByRole('combobox')).toHaveCount(group.subjects.length)
    for (const row of group.subjects) await expect(page.getByRole('combobox', { name: `Professor de ${row.subject_name}`, exact: true })).toHaveValue(String(row.teacher_id))
  }
  await page.reload()
  expect(isDeepStrictEqual(validateImportedData(original, await readImportedData(page)), identities), 'Imported identities and relations survive a UI reload').toBe(true)
  if (testInfo) {
    await testInfo.attach('imported-entity-relations-observation', {
      body: Buffer.from(JSON.stringify({ identities_verified: true, reload_preserved: true })), contentType: 'application/json',
    })
    await recordCheckpoint(testInfo, ['E2E-05/entity-relations', 'E2E-05/reload-persistence'], { requires: 'school' })
  }
  return { identities, snapshot }
}

export async function inviteImportedTeacher(page, original, before, email, testInfo) {
  const importedEmail = Object.keys(original.teachers)[0]
  const teacherId = before.identities.teachers[importedEmail]
  const members = await readSchoolResource(page, 'members/?limit=100&skip=0')
  if (members.total !== members.items.length) throw new Error('Imported member inventory is incomplete')
  const member = members.items.find(row => row.teacher_id === teacherId && row.email === importedEmail)
  expect(member?.teacher_access_mode).toBe('scheduler_only')
  expect(member?.access_status).not.toBe('active')
  await page.goto('/members')
  const row = page.getByRole('row').filter({ has: page.getByText(importedEmail, { exact: true }) })
  await row.getByRole('button', { name: 'Editar membro', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Editar membro', exact: true })).toBeVisible()
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Acesso do professor', { exact: true }).selectOption('platform')
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/members/${member.id}` && response.request().method() === 'PATCH')
  const requestedAt = Date.now()
  await page.getByRole('button', { name: 'Guardar', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  const invited = await response.json()
  expect(invited.id).toBe(member.id)
  expect(invited.account_id).toBe(member.account_id)
  expect(invited.teacher_id).toBe(teacherId)
  expect(invited.subject_ids.toSorted()).toEqual(member.subject_ids.toSorted())
  expect(invited.access_status).toBe('pending_invite')
  expect(invited.clerk_invitation_id).toMatch(/^orginv_/)
  await expect(page.getByRole('heading', { name: 'Editar membro', exact: true })).toHaveCount(0)
  const converted = structuredClone(original)
  converted.teachers[email] = converted.teachers[importedEmail]
  delete converted.teachers[importedEmail]
  for (const assignment of converted.demand) if (assignment.teacher === importedEmail) assignment.teacher = email
  const identities = structuredClone(before.identities)
  identities.teachers[email] = identities.teachers[importedEmail]
  delete identities.teachers[importedEmail]
  expect(isDeepStrictEqual(validateImportedData(converted, await readImportedData(page)), identities), 'Invitation preserves every imported identity, competency and assignment').toBe(true)
  if (testInfo) {
    await testInfo.attach('original-imported-teacher-invitation', {
      body: Buffer.from(JSON.stringify({ member_id: invited.id, access_status: invited.access_status, clerk_invitation_id: invited.clerk_invitation_id })), contentType: 'application/json',
    })
  }
  return { original: converted, identities, member: invited, requestedAt }
}

export async function verifyAcceptedTeacher(page, converted) {
  const members = await readSchoolResource(page, 'members/?limit=100&skip=0')
  if (members.total !== members.items.length) throw new Error('Accepted member inventory is incomplete')
  const member = members.items.find(row => row.id === converted.member.id)
  expect(member?.access_status).toBe('active')
  expect(member?.teacher_id).toBe(converted.member.teacher_id)
  expect(member?.account_id).toBe(converted.member.account_id)
  expect(member?.subject_ids.toSorted()).toEqual(converted.member.subject_ids.toSorted())
  expect(isDeepStrictEqual(validateImportedData(converted.original, await readImportedData(page)), converted.identities), 'Accepted teacher preserves every imported relation').toBe(true)
}

export async function archiveAndRestoreCampaignTeacher(page, converted, testInfo) {
  const expectedEmail = `professorcronos100+${process.env.E2E_RUN_ID}@gmail.com`
  expect(converted.member.email).toBe(expectedEmail)
  const member = await readSchoolResource(page, `members/${converted.member.id}`)
  expect(member.email).toBe(expectedEmail)
  expect(member.teacher_id).toBe(converted.member.teacher_id)
  expect(member.account_id).toBe(converted.member.account_id)
  expect(member.access_status).toBe('active')
  expect(member.remove_effect).toBe('archive')
  const row = page.getByRole('row').filter({ has: page.getByText(expectedEmail, { exact: true }) })
  await page.goto('/members')
  await row.getByRole('button', { name: 'Remover membro', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('Este membro tem histórico e será arquivado para preservar horários, aulas e auditoria.', { exact: true })).toBeVisible()
  const removed = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/members/${member.id}/remove` && response.request().method() === 'POST')
  await page.getByRole('dialog').getByRole('button', { name: 'Remover', exact: true }).click()
  expect((await removed).status()).toBe(200)
  await expect(row).toHaveCount(0)
  const archived = await readSchoolResource(page, `members/${member.id}`)
  expect(archived.lifecycle_status).toBe('archived')
  expect(archived.teacher_id).toBe(member.teacher_id)
  expect(archived.account_id).toBe(member.account_id)
  expect(archived.subject_ids.toSorted()).toEqual(member.subject_ids.toSorted())
  await page.getByLabel('Mostrar arquivados', { exact: true }).check()
  const restored = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/members/${member.id}/restore` && response.request().method() === 'POST')
  await row.getByRole('button', { name: 'Restaurar membro', exact: true }).click()
  expect((await restored).status()).toBe(200)
  await page.getByLabel('Mostrar arquivados', { exact: true }).uncheck()
  await page.reload()
  await expect(row.getByRole('button', { name: 'Remover membro', exact: true })).toBeEnabled()
  await verifyAcceptedTeacher(page, converted)
  if (testInfo) {
    await testInfo.attach('archived-and-restored-teacher', {
      body: Buffer.from(JSON.stringify({ member_id: member.id, lifecycle_status: archived.lifecycle_status, restored: true })), contentType: 'application/json',
    })
    await recordCheckpoint(testInfo, 'E2E-06/archive-restore', {
      requires: 'school', observation: { member_id: member.id, lifecycle_status: archived.lifecycle_status },
    })
  }
}

export function futureSchoolPeriod(now = new Date()) {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Lisbon', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const start = new Date(`${today}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() + 1)
  const shift = days => new Date(start.getTime() + days * 86_400_000).toISOString().slice(0, 10)
  return { start: shift(0), preferred: shift(270), hard: shift(365) }
}

const displayDate = value => value.split('-').reverse().join('/')

export async function completeFoundation(page, period, testInfo, { checkpoint = true } = {}) {
  await page.goto('/foundation')
  await expect(page.getByRole('heading', { name: '1. Período do Ano Letivo', exact: true })).toBeVisible()
  for (const [id, value] of [['school_start_date', period.start], ['school_hard_end_date', period.hard]]) {
    await page.locator(`#${id}`).fill(displayDate(value))
    await page.locator(`#${id}`).press('Tab')
  }
  await expect(page.locator('#preferred_end_date')).toHaveValue('')
  const next = page.getByRole('button', { name: /^(Seguinte|Ignorar por agora)/ })
  await next.click()
  await expect(page.getByRole('heading', { name: '2. Dias de Funcionamento Letivo', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /Anterior$/ }).click()
  await expect(page.locator('#preferred_end_date')).toHaveValue('')
  for (const [boundary, offset] of [[period.start, -1], [period.hard, 1]]) {
    const invalid = new Date(Date.parse(`${boundary}T00:00:00Z`) + offset * 86_400_000).toISOString().slice(0, 10)
    await page.locator('#preferred_end_date').fill(displayDate(invalid))
    await page.locator('#preferred_end_date').press('Tab')
    await next.click()
    await expect(page.getByRole('heading', { name: '1. Período do Ano Letivo', exact: true })).toBeVisible()
    await expect(page.getByText('A data preferencial deve ficar entre o início das aulas e a data-limite.', { exact: true })).toBeVisible()
  }
  const saved = page.waitForResponse(response => {
    if (new URL(response.url()).pathname !== '/api/v1/foundation/draft' || response.request().method() !== 'PUT') return false
    const data = response.request().postDataJSON()?.data
    return data?.preferred_end_date === period.preferred && data?.school_start_date === period.start && data?.school_hard_end_date === period.hard
  })
  await page.locator('#preferred_end_date').fill(displayDate(period.preferred))
  await page.locator('#preferred_end_date').press('Tab')
  expect((await saved).status()).toBe(200)
  await expect(next).toBeEnabled()
  await page.reload()
  await expect(page.locator('#school_start_date')).toHaveValue(displayDate(period.start))
  await expect(page.locator('#school_hard_end_date')).toHaveValue(displayDate(period.hard))
  await expect(page.locator('#preferred_end_date')).toHaveValue(displayDate(period.preferred))
  for (let step = 1; step < 10; step++) {
    await expect(page.getByRole('heading', { name: new RegExp(`^${step}\\. `) })).toBeVisible()
    if (step === 8) await expect(page.getByRole('checkbox', { name: /feriados automáticos/i })).not.toBeChecked()
    await next.click()
  }
  await expect(page.getByRole('heading', { name: '10. Confirmação e Ativação da Fundação', exact: true })).toBeVisible()
  for (const value of [period.start, period.preferred, period.hard]) await expect(page.getByText(value, { exact: true })).toBeVisible()
  await page.getByRole('checkbox', { name: 'Confirmo que revi os dados e autorizo a ativação da escola.', exact: true }).check()
  await page.getByRole('button', { name: 'Ativar Escola', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/config')
  await page.reload()
  for (const [id, value] of [['startDate', period.start], ['hardEndDate', period.hard], ['preferredEndDate', period.preferred]]) {
    await expect(page.locator(`#${id}`)).toHaveValue(displayDate(value))
  }
  if (checkpoint && testInfo) {
    await recordCheckpoint(testInfo, [
      'E2E-01/foundation-completion', 'E2E-07/ten-foundation-steps', 'E2E-07/preferred-date-draft', 'E2E-07/calendar-persistence',
    ], { requires: 'school', observation: { steps: 10, start: period.start, preferred: period.preferred, hard: period.hard } })
  }
}

export async function importOriginalData(page, testInfo, { checkpoint = true } = {}) {
  const files = {
    rooms: 'Folha de cálculo sem nome - Cronos_Salas_Template_Maior.csv',
    subjects: 'Cronos_DisciplinasEModulos_Template_Maior.csv',
    courses: 'Cronos_CursosETurmas_Template_Maior.csv',
    teachers: 'Cronos_ProfessoresECompetencias_Template_Maior.csv',
    assignments: 'Cronos_Atribuicoes_Template_Maior.csv',
  }
  await page.goto('/imports')
  for (const [resource, filename] of Object.entries(files)) {
    const originalPath = fileURLToPath(new URL(`../data/originals/${filename}`, import.meta.url))
    const templateName = resource === 'rooms' ? 'Cronos_Salas_Template.csv' : filename.replace('_Maior.csv', '.csv')
    const downloading = page.waitForEvent('download')
    await page.locator('.card').filter({ has: page.locator(`#import-${resource}`) }).getByRole('button', { name: 'Descarregar modelo', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    expect(download.suggestedFilename()).toBe(templateName)
    const path = testInfo.outputPath(templateName)
    await download.saveAs(path)
    const bytes = await readFile(path)
    // The app's models use ';' (Portuguese spreadsheets); the owner's files use ','.
    // The importer detects the delimiter, so the columns are what must match.
    const columns = value => value.replace(/^\uFEFF/, '').split(/\r?\n/)[0].split(/[;,]/).map(column => column.trim())
    expect(columns(bytes.toString('utf8'))).toEqual(columns(await readFile(originalPath, 'utf8')))
    expect(bytes.toString('utf8').split(/\r?\n/).filter(line => line.trim()).length).toBeGreaterThan(1)
    await testInfo.attach(`downloaded-${resource}-model`, { path, contentType: 'text/csv' })
    await page.locator(`#import-${resource}`).setInputFiles(originalPath)
  }
  await page.getByRole('button', { name: 'Verificar ficheiros', exact: true }).click()
  const report = page.getByRole('region', { name: 'Resultado da verificação', exact: true })
  await expect(report.getByText('Sem erros', { exact: true })).toBeVisible()
  for (const [label, count] of Object.entries({ Salas: 48, Disciplinas: 52, Módulos: 208, Cursos: 16, Turmas: 48, Professores: 40, Atribuições: 336 })) {
    await expect(report.getByText(`${label}: ${count}`, { exact: true })).toBeVisible()
  }
  await testInfo.attach('original-import-validation', { body: await report.screenshot(), contentType: 'image/png' })
  const committed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/imports/commit' && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar importação', exact: true }).click()
  const response = await committed
  expect(response.status()).toBe(201)
  const result = await response.json()
  expect(result.created_counts).toMatchObject({ rooms: 48, subjects: 52, modules: 208, courses: 16, classes: 48, teachers: 40, assignments: 336 })
  await testInfo.attach('original-import-result', { body: Buffer.from(JSON.stringify(result)), contentType: 'application/json' })
  await expect(page).toHaveURL(/\/rooms$/)
  await expect(page.getByText('Importação concluída.', { exact: true })).toBeVisible()
  if (checkpoint) {
    await recordCheckpoint(testInfo, ['E2E-05/five-original-imports', 'E2E-05/import-report', 'E2E-16/five-model-downloads'], {
      requires: 'school', observation: { created_counts: result.created_counts },
    })
  }
}
