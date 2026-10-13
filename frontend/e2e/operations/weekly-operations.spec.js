import { expect, test } from '@playwright/test'
import { formatDateLong } from '../../src/utils/formatUtils.js'
import {
  allowApiFailure,
  attachRuntimeGuards,
  goTo,
  loginAsAdminReal,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'
import {
  apiRequest,
  generateAndApproveThroughUi,
  seedMinimalSchedulerInputs,
} from '../utils/scheduler-fixtures.js'

const DAY_MS = 86_400_000
const addDays = (isoDate, days) => new Date(Date.parse(`${isoDate}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)
const isApi = (response, path, method) => new URL(response.url()).pathname === `/api/v1/${path}`
  && response.request().method() === method

// The CI school year starts two weeks in the past, so these lessons really ended.
async function firstEndedWeek(page, horizon) {
  const today = new Date().toISOString().slice(0, 10)
  for (let weekStart = horizon.min_week_start; weekStart <= today; weekStart = addDays(weekStart, 7)) {
    const rows = await apiRequest(page, 'GET', `/schedule/week?week_start=${weekStart}`)
    const lessons = rows.filter((row) => row.scheduler_lesson_id)
    if (lessons.length >= 2 && lessons.length === rows.length
      && rows.every((row) => Date.parse(row.ends_at) <= Date.now() && !row.lesson_log_id && row.week_timesheet_status === 'OPEN')) {
      return { weekStart, rows: [...rows].sort((a, b) => Date.parse(a.ends_at) - Date.parse(b.ends_at)) }
    }
  }
  throw new Error('The CI school year has no ended, open week with two lessons')
}

async function openTeacherWeek(page, horizon, weekStart) {
  await goTo(page, '/my-schedules')
  await expect(page.getByText('Horário publicado', { exact: true })).toBeVisible()
  let visibleWeek = horizon.week_start_recommended
  const direction = visibleWeek > weekStart ? 'Semana anterior' : 'Próxima semana'
  while (visibleWeek !== weekStart) {
    const requested = addDays(visibleWeek, direction === 'Semana anterior' ? -7 : 7)
    const loaded = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/schedule/week'
      && new URL(response.url()).searchParams.get('week_start') === requested)
    await page.getByRole('button', { name: direction, exact: true }).click()
    expect((await loaded).status()).toBe(200)
    visibleWeek = requested
  }
}

// The same subject can repeat in a week: match the lesson's own interval, class and date.
async function openLessonRecord(page, row, status) {
  const cells = page.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
    .getByRole('gridcell', { name: `${row.subject.name}, ${row.teacher.name}, ${row.room.name}, ${status}`, exact: true })
  await expect(cells.first()).toBeVisible()
  const interval = `${row.timeslot.start_time} – ${row.timeslot.end_time}`
  for (const cell of await cells.all()) {
    await cell.getByRole('button', { name: `Abrir registo de ${row.subject.name}`, exact: true }).click()
    const dialog = page.getByRole('dialog')
    const text = await dialog.innerText()
    if (text.includes(interval) && text.includes(row.class_info.name) && text.includes(formatDateLong(row.date))) return dialog
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  throw new Error(`Lesson ${row.scheduler_lesson_id} is not visible in the week grid`)
}

async function recordLesson(page, row, summary, action) {
  const dialog = await openLessonRecord(page, row, 'Planeado')
  await dialog.getByLabel('Sumário', { exact: true }).fill(summary)
  const saved = page.waitForResponse((response) => isApi(response, `schedule/lessons/${row.scheduler_lesson_id}/log`, 'PUT'))
  await dialog.getByRole('button', { name: action, exact: true }).click()
  if (action === 'Criar Ocorrência') {
    await expect(dialog.getByText('Criar ocorrência?', { exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: 'Sim, criar ocorrência', exact: true }).click()
  }
  expect((await saved).status()).toBe(200)
  await expect(page.getByText('Registo guardado.', { exact: true })).toBeVisible()
  await expect(dialog).toBeHidden()
}

async function decideGiven(page, occurrence) {
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Dada', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeDisabled()
  await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
  const decided = page.waitForResponse((response) => isApi(response, `occurrences/${occurrence.id}`, 'PATCH'))
  await dialog.getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
  const response = await decided
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({
    status: 'GIVEN', version: occurrence.version, substitute_teacher_id: null, substitute_subject_id: null,
  })
  await expect(page.getByText('Decisão registada.', { exact: true })).toBeVisible()
}

async function openTimesheetWeek(page, weekStart) {
  const roster = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/timesheets/'
    && new URL(response.url()).searchParams.has('week_start_date'))
  await goTo(page, '/timesheets')
  await expect(page.getByRole('heading', { name: 'Fecho Semanal', exact: true })).toBeVisible()
  let visibleWeek = new URL((await roster).url()).searchParams.get('week_start_date')
  while (visibleWeek !== weekStart) {
    const backwards = visibleWeek > weekStart
    const requested = addDays(visibleWeek, backwards ? -7 : 7)
    const loaded = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/timesheets/'
      && new URL(response.url()).searchParams.get('week_start_date') === requested)
    await page.getByRole('button', { name: backwards ? 'Semana anterior' : 'Próxima semana', exact: true }).click()
    expect((await loaded).status()).toBe(200)
    visibleWeek = requested
  }
}

test('teacher records ended lessons, admin decides the occurrence and closes the week', async ({ page, browser }) => {
  test.setTimeout(300_000)
  attachRuntimeGuards(page)
  allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
  await loginAsAdminReal(page)
  await goTo(page, '/dashboard')
  await seedMinimalSchedulerInputs(page)
  await generateAndApproveThroughUi(page)

  const teacherContext = await browser.newContext()
  try {
    const teacherPage = await teacherContext.newPage()
    attachRuntimeGuards(teacherPage)
    await loginAsTeacherReal(teacherPage)
    const horizon = await apiRequest(teacherPage, 'GET', '/schedule/me/horizon')
    const week = await firstEndedWeek(teacherPage, horizon)
    const weekPath = `/schedule/week?week_start=${week.weekStart}`
    const occurrenceRow = week.rows.at(-1)
    const debtsBefore = await apiRequest(page, 'GET', '/occurrences/debts')

    await test.step('teacher cannot submit a week with unregistered lessons', async () => {
      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      await expect(teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })).toBeDisabled()
    })

    await test.step('teacher records given lessons and an occurrence through the lesson dialog', async () => {
      for (const row of week.rows.slice(0, -1)) {
        await recordLesson(teacherPage, row, `CI: aula ${row.scheduler_lesson_id} dada.`, 'Aula Dada')
      }
      await recordLesson(teacherPage, occurrenceRow, 'CI: ocorrência após o término.', 'Criar Ocorrência')
      const rows = await apiRequest(teacherPage, 'GET', weekPath)
      for (const row of rows) {
        expect(row.lesson_log_status).toBe(row.scheduler_lesson_id === occurrenceRow.scheduler_lesson_id ? 'OCCURRENCE' : 'COMPLETED')
      }
      // A pending occurrence creates no debt before the admin decides it.
      expect(await apiRequest(page, 'GET', '/occurrences/debts')).toEqual(debtsBefore)
    })

    await test.step('admin decides the occurrence as given, and repeating it changes nothing', async () => {
      const row = (await apiRequest(teacherPage, 'GET', weekPath)).find((item) => item.scheduler_lesson_id === occurrenceRow.scheduler_lesson_id)
      expect(row.occurrence_id).toBeGreaterThan(0)
      const pending = await apiRequest(page, 'GET', `/occurrences/${row.occurrence_id}`)
      expect(pending).toMatchObject({ operational_state: 'OPEN_PENDING', decided_at: null })
      await goTo(page, `/absences?occurrence_id=${pending.id}`)
      await decideGiven(page, pending)
      const given = await apiRequest(page, 'GET', `/occurrences/${pending.id}`)
      expect(given).toMatchObject({ id: pending.id, operational_state: 'DECIDED_GIVEN', substitute_block_id: null })
      expect(await apiRequest(page, 'GET', '/occurrences/debts')).toEqual(debtsBefore)

      await page.reload()
      await decideGiven(page, given)
      expect(await apiRequest(page, 'GET', `/occurrences/${pending.id}`)).toEqual(given)
      expect(await apiRequest(page, 'GET', '/occurrences/debts')).toEqual(debtsBefore)
    })

    let timesheet
    await test.step('teacher submits the fully registered week', async () => {
      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      const submit = teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })
      await expect(submit).toBeEnabled()
      await submit.click()
      const submitted = teacherPage.waitForResponse((response) => isApi(response, `timesheets/me/${week.weekStart}/submit`, 'POST'))
      await teacherPage.getByRole('dialog').getByRole('button', { name: 'Submeter', exact: true }).click()
      const response = await submitted
      expect(response.status()).toBe(200)
      timesheet = await response.json()
      expect(timesheet).toMatchObject({ status: 'SUBMITTED', week_start_date: week.weekStart })
      await expect(teacherPage.getByText('Semana submetida.', { exact: true })).toBeVisible()
    })

    await test.step('admin approves the week and the teacher can no longer edit it', async () => {
      await openTimesheetWeek(page, week.weekStart)
      const roster = await apiRequest(page, 'GET', `/timesheets/?week_start_date=${week.weekStart}`)
      const record = roster.find((item) => item.id === timesheet.id)
      expect(record).toMatchObject({ status: 'SUBMITTED', total_slots: week.rows.length, registered_slots: week.rows.length })
      await page.getByRole('button').filter({ hasText: record.teacher_name }).click()
      const approved = page.waitForResponse((response) => isApi(response, `timesheets/${timesheet.id}/status`, 'PATCH'))
      await page.getByRole('button', { name: 'Aprovar', exact: true }).click()
      const response = await approved
      expect(response.status()).toBe(200)
      expect(response.request().postDataJSON()).toEqual({ status: 'APPROVED' })
      await expect(page.getByText('Semana aprovada.', { exact: true })).toBeVisible()

      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      const closed = await apiRequest(teacherPage, 'GET', weekPath)
      expect(closed.every((row) => row.week_timesheet_status === 'APPROVED' && !row.can_complete)).toBe(true)
      await expect(teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })).toBeDisabled()
      const locked = await openLessonRecord(teacherPage, week.rows[0], 'Concluída')
      await expect(locked.getByLabel('Sumário', { exact: true })).toBeDisabled()
      await expect(locked.getByRole('button', { name: 'Guardar alterações', exact: true })).toHaveCount(0)
      await locked.getByRole('button', { name: 'Cancelar', exact: true }).click()
    })

    await test.step('admin reopens the week and the teacher can edit again', async () => {
      await page.getByRole('button', { name: 'Reabrir', exact: true }).click()
      const reopened = page.waitForResponse((response) => isApi(response, `timesheets/${timesheet.id}/status`, 'PATCH'))
      const confirmation = page.getByRole('dialog')
      await expect(confirmation).toContainText('Confirmar Reabertura')
      await confirmation.getByRole('button', { name: 'Sim, reabrir', exact: true }).click()
      const response = await reopened
      expect(response.status()).toBe(200)
      expect(response.request().postDataJSON()).toEqual({ status: 'OPEN' })
      await expect(page.getByText('Semana reaberta.', { exact: true })).toBeVisible()

      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      const open = await apiRequest(teacherPage, 'GET', weekPath)
      expect(open.every((row) => row.week_timesheet_status === 'OPEN')).toBe(true)
      const editable = await openLessonRecord(teacherPage, week.rows[0], 'Concluída')
      await expect(editable.getByLabel('Sumário', { exact: true })).toBeEnabled()
      await expect(editable.getByRole('button', { name: 'Guardar alterações', exact: true })).toBeEnabled()
      await editable.getByRole('button', { name: 'Cancelar', exact: true }).click()
    })
  } finally {
    await teacherContext.close()
  }
})
