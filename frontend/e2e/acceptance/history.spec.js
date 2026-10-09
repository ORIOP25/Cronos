import { lstat, readFile } from 'node:fs/promises'
import { verifyRegistry } from '../../../scripts/e2e-run-registry.mjs'
import { recordCheckpoint } from '../utils/acceptance-proof.js'
import { freshSession, loginPersistentActor } from '../utils/ui-auth.js'
import { readSchoolResource } from '../utils/ui-school.js'
import { validateExecutedLessonCredit } from '../utils/expected-results.js'
import { openLessonRecord, openTeacherWeek } from '../utils/ui-teacher.js'
import { exerciseEndedGiven, exerciseEndedSubstitution } from '../utils/ui-occurrences.js'
import { exerciseHistoricalWeek } from '../utils/ui-timesheets.js'
import { exerciseHistoricalRepair } from '../utils/ui-repair.js'
import { test, expect } from './fixtures.js'

function nextWeek(value) {
  return new Date(Date.parse(`${value}T00:00:00Z`) + 7 * 86_400_000).toISOString().slice(0, 10)
}

test('persistent UI school records an ended lesson once and preserves exact curricular credit', {
  annotation: ['E2E-10/ended-lesson-log', 'E2E-10/exact-minute-delta', 'E2E-10/repeat-without-duplicate', 'E2E-11/given-decision', 'E2E-11/ended-substitution-credit', 'E2E-11/reversal-compensations',
    'E2E-12/submit-week', 'E2E-12/approve-week', 'E2E-12/closed-week-blocked', 'E2E-12/reopen-week',
    'E2E-13/future-change-repair', 'E2E-13/physical-lineage', 'E2E-13/residual-coverage', 'E2E-13/historical-credit-preserved']
    .map(description => ({ type: 'acceptance-case', description })),
}, async ({ page, browser, provenance, registerSecret }, testInfo) => {
  test.setTimeout(1_800_000)
  const path = process.env.E2E_PERSISTENT_REGISTRY
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Persistent UI registry must be a regular file')
  const registry = verifyRegistry(JSON.parse(await readFile(path, 'utf8')), Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'))
  const schools = registry.organizations?.filter(item => item.type === 'persistent' && item.provenance === 'ui') || []
  const school = schools[0]
  if (!school || school.preparation?.status !== 'prepared' || school.preparation.history_verified !== false
    || !/^[a-z0-9-]+$/.test(school.creation_run_id || '') || !/^org_[a-zA-Z0-9]+$/.test(school.clerk_id || '')
    || !Number.isSafeInteger(school.local_id) || school.local_id <= 0
    || !Number.isFinite(Date.parse(school.created_at)) || Date.parse(school.created_at) >= Date.now()) {
    throw new Error('Historical dependency unavailable: a signed persistent school created through the UI is required')
  }
  const email = `professorcronos100+${school.creation_run_id}@gmail.com`
  const actor = school.actors?.find(item => item.email === email && item.provenance === 'ui' && item.creation_run_id === school.creation_run_id)
  const password = process.env.E2E_HISTORY_TEACHER_PASSWORD
  const adminPassword = process.env.E2E_HISTORY_ADMIN_PASSWORD
  const adminActor = school.actors?.find(item => item.id === school.creator_id && item.email === `admincronos100+${school.creation_run_id}@gmail.com` && item.provenance === 'ui')
  if (!actor || !password || !adminActor || !adminPassword) throw new Error('Historical dependency unavailable: persistent teacher and founder UI credentials are required')
  await registerSecret(password)
  await registerSecret(adminPassword)
  const member = await loginPersistentActor(page, school, actor, password)
  expect(member.teacher_id).toBe(school.preparation.teacher_id)
  expect(member.capabilities).toContain('teacher')
  await provenance.observePersistentSchool(school, page)
  await page.goto('/my-schedules')
  await expect(page.getByText('Horário publicado', { exact: true })).toBeVisible()
  const horizon = await readSchoolResource(page, 'schedule/me/horizon')
  const weeks = []
  let selected
  for (let weekStart = horizon.min_week_start; weekStart && weekStart <= horizon.hard_end_date && weekStart <= new Date().toISOString().slice(0, 10); weekStart = nextWeek(weekStart)) {
    const rows = await readSchoolResource(page, `schedule/week?week_start=${weekStart}`)
    weeks.push({ weekStart, rows })
    const row = rows.find(item => item.teacher?.id === member.teacher_id && item.scheduler_lesson_id
      && item.block_source === 'planned' && !item.lesson_log_id && !item.occurrence_id
      && item.week_timesheet_status === 'OPEN' && item.can_complete === true
      && Date.parse(item.ends_at) > Date.parse(school.created_at) && Date.parse(item.ends_at) <= Date.now()
      && item.slices.length && item.slices.every(slice => slice.completed_minutes === slice.offset_minutes && slice.remaining_minutes >= slice.minutes))
    if (row) { selected = { weekStart, row }; break }
  }
  if (!selected) throw new Error('Historical dependency unavailable: no ended, unregistered lesson at the real curricular frontier')
  await openTeacherWeek(page, horizon, selected.weekStart)
  const endpoint = `/api/v1/schedule/lessons/${selected.row.scheduler_lesson_id}/log`
  const weekPath = `schedule/week?week_start=${selected.weekStart}`
  const beforeProgress = await readSchoolResource(page, 'teachers/me/progress')
  const summary = `Aceitação ${process.env.E2E_RUN_ID}: aula terminada.`
  let dialog = await openLessonRecord(page, selected.row, 'Planeado')
  await dialog.getByLabel('Sumário', { exact: true }).fill(summary)
  await expect(dialog.getByRole('button', { name: 'Aula Dada', exact: true })).toBeEnabled()
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'PUT')
  await dialog.getByRole('button', { name: 'Aula Dada', exact: true }).click()
  const savedResponse = await saved
  expect(savedResponse.status()).toBe(200)
  expect(savedResponse.request().postDataJSON()).toEqual({ status: 'COMPLETED', summary, notes: '' })
  await expect(page.getByText('Registo guardado.', { exact: true })).toBeVisible()
  await openTeacherWeek(page, horizon, selected.weekStart)
  const afterWeek = await readSchoolResource(page, weekPath)
  const after = afterWeek.find(row => row.scheduler_lesson_id === selected.row.scheduler_lesson_id)
  const minutes = validateExecutedLessonCredit(selected.row, after)
  expect(after.lesson_log_summary).toBe(summary)
  expect(Date.parse(after.lesson_log_logged_at)).toBeGreaterThanOrEqual(Date.parse(after.ends_at))
  const afterProgress = await readSchoolResource(page, 'teachers/me/progress')
  dialog = await openLessonRecord(page, after, 'Concluída')
  await expect(dialog.getByRole('button', { name: 'Aula Dada', exact: true })).toHaveCount(0)
  await dialog.getByLabel('Sumário', { exact: true }).fill(`${summary} Texto revisto.`)
  const repeated = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'PUT')
  await dialog.getByRole('button', { name: 'Guardar alterações', exact: true }).click()
  expect((await repeated).status()).toBe(200)
  await expect(page.getByText('Registo guardado.', { exact: true })).toBeVisible()
  const repeatedRow = (await readSchoolResource(page, weekPath)).find(row => row.scheduler_lesson_id === after.scheduler_lesson_id)
  expect(repeatedRow.lesson_log_id).toBe(after.lesson_log_id)
  expect(repeatedRow.slices).toEqual(after.slices)
  expect(repeatedRow.lesson_log_summary).toBe(`${summary} Texto revisto.`)
  expect(await readSchoolResource(page, 'teachers/me/progress')).toEqual(afterProgress)
  await testInfo.attach('ended-lesson-exact-credit-and-idempotent-summary', {
    body: Buffer.from(JSON.stringify({ organization_id: school.local_id, creation_run_id: school.creation_run_id,
      week_start: selected.weekStart, before: selected.row, after, repeated: repeatedRow, exact_minutes: minutes,
      inspected_weeks: weeks.length, beforeProgress, afterProgress })), contentType: 'application/json',
  })
  await recordCheckpoint(testInfo, [
    'E2E-10/ended-lesson-log', 'E2E-10/exact-minute-delta', 'E2E-10/repeat-without-duplicate',
  ], { requires: 'school', observation: { lesson_log_id: after.lesson_log_id, exact_minutes: minutes } })
  await freshSession(browser, testInfo, 'persistent-admin-occurrence-decisions', async adminPage => {
    const admin = await loginPersistentActor(adminPage, school, adminActor, adminPassword)
    expect(admin.capabilities).toContain('admin')
    await exerciseEndedGiven(page, adminPage, testInfo, school, horizon, selected.weekStart)
    await exerciseEndedSubstitution(page, adminPage, testInfo, school, horizon, selected.weekStart)
    await exerciseHistoricalWeek(page, adminPage, testInfo, school, horizon, member.teacher_id)
    await exerciseHistoricalRepair(page, adminPage, testInfo, school, horizon, selected.weekStart)
  })
})
