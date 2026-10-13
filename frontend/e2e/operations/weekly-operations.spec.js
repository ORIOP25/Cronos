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

// The engine publishes only into periods that have not started, so every lesson is still ahead.
async function firstPublishedWeek(page, horizon) {
  for (let weekStart = horizon.min_week_start; weekStart <= horizon.hard_end_date; weekStart = addDays(weekStart, 7)) {
    const rows = (await apiRequest(page, 'GET', `/schedule/week?week_start=${weekStart}`)).filter((row) => row.scheduler_lesson_id)
    if (rows.length) return { weekStart, rows: [...rows].sort((a, b) => Date.parse(a.ends_at) - Date.parse(b.ends_at)) }
  }
  throw new Error('The published CI schedule has no lessons for the teacher')
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

async function decideGap(page, occurrence) {
  const dialog = page.getByRole('dialog')
  // A lesson that has not ended cannot be decided as given.
  await expect(dialog.getByRole('button', { name: 'Dada', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Furo', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeDisabled()
  await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
  const decided = page.waitForResponse((response) => isApi(response, `occurrences/${occurrence.id}`, 'PATCH'))
  await dialog.getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
  const response = await decided
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({
    status: 'GAP', version: occurrence.version, substitute_teacher_id: null, substitute_subject_id: null,
  })
  await expect(page.getByText('Decisão registada.', { exact: true })).toBeVisible()
}

test('teacher records an occurrence in advance and the admin decides it once', async ({ page, browser }) => {
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
    const week = await firstPublishedWeek(teacherPage, horizon)
    const weekPath = `/schedule/week?week_start=${week.weekStart}`
    const lesson = week.rows[0]
    const debtsBefore = await apiRequest(page, 'GET', '/occurrences/debts')
    const writes = []
    teacherPage.on('request', (request) => {
      if (new URL(request.url()).pathname.startsWith('/api/v1/') && request.method() !== 'GET') writes.push(request.method())
    })

    await test.step('teacher cannot execute a lesson or submit a week before the lessons end', async () => {
      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      const submit = teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })
      await expect(submit).toBeDisabled()
      await expect(submit).toHaveAttribute('title', /aula futura.*não registada/)
      const dialog = await openLessonRecord(teacherPage, lesson, 'Planeado')
      await expect(dialog.getByText(
        'Só pode concluir esta aula depois do seu término. Pode preencher o sumário e criar ocorrência antecipadamente.',
        { exact: true },
      )).toBeVisible()
      await dialog.getByLabel('Sumário', { exact: true }).fill('CI: aula ainda por dar.')
      await expect(dialog.getByRole('button', { name: 'Aula Dada', exact: true })).toBeDisabled()
      await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
      await expect(teacherPage.getByRole('dialog')).toHaveCount(0)
      expect(writes).toEqual([])
    })

    let occurrence
    await test.step('teacher creates the occurrence in advance through the lesson dialog', async () => {
      const dialog = await openLessonRecord(teacherPage, lesson, 'Planeado')
      await dialog.getByLabel('Sumário', { exact: true }).fill('CI: falta prevista.')
      await dialog.getByRole('button', { name: 'Criar Ocorrência', exact: true }).click()
      await expect(dialog.getByText('Criar ocorrência?', { exact: true })).toBeVisible()
      const saved = teacherPage.waitForResponse((response) => isApi(response, `schedule/lessons/${lesson.scheduler_lesson_id}/log`, 'PUT'))
      await dialog.getByRole('button', { name: 'Sim, criar ocorrência', exact: true }).click()
      const response = await saved
      expect(response.status()).toBe(200)
      expect(response.request().postDataJSON()).toEqual({ status: 'OCCURRENCE', summary: 'CI: falta prevista.', notes: '' })
      await expect(teacherPage.getByText('Registo guardado.', { exact: true })).toBeVisible()
      await expect(dialog).toBeHidden()

      const row = (await apiRequest(teacherPage, 'GET', weekPath)).find((item) => item.scheduler_lesson_id === lesson.scheduler_lesson_id)
      expect(row).toMatchObject({ lesson_log_status: 'OCCURRENCE', can_complete: false })
      occurrence = await apiRequest(page, 'GET', `/occurrences/${row.occurrence_id}`)
      expect(occurrence).toMatchObject({ operational_state: 'OPEN_PENDING', decided_at: null })
      // A pending occurrence creates no debt before the admin decides it.
      expect(await apiRequest(page, 'GET', '/occurrences/debts')).toEqual(debtsBefore)
    })

    await test.step('admin decides the gap once, and repeating it changes nothing', async () => {
      await goTo(page, `/absences?occurrence_id=${occurrence.id}`)
      await decideGap(page, occurrence)
      const gap = await apiRequest(page, 'GET', `/occurrences/${occurrence.id}`)
      expect(gap).toMatchObject({ id: occurrence.id, operational_state: 'DECIDED_GAP' })
      const debtsAfter = await apiRequest(page, 'GET', '/occurrences/debts')
      expect(debtsAfter.total_hours_owed).toBeGreaterThan(debtsBefore.total_hours_owed)

      await page.reload()
      await decideGap(page, gap)
      expect(await apiRequest(page, 'GET', `/occurrences/${occurrence.id}`)).toEqual(gap)
      expect(await apiRequest(page, 'GET', '/occurrences/debts')).toEqual(debtsAfter)
    })

    await test.step('teacher sees the decided gap in the published week', async () => {
      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      const row = (await apiRequest(teacherPage, 'GET', weekPath)).find((item) => item.scheduler_lesson_id === lesson.scheduler_lesson_id)
      expect(row).toMatchObject({ occurrence_id: occurrence.id, occurrence_status: 'GAP' })
      await expect(teacherPage.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
        .getByRole('gridcell', { name: `${lesson.subject.name}, ${lesson.teacher.name}, ${lesson.room.name}, Falta ✗`, exact: true })
        .first()).toBeVisible()
    })
  } finally {
    await teacherContext.close()
  }
})
