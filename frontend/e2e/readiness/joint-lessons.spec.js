import { expect, test } from '@playwright/test'
import { formatDateLong } from '../../src/utils/formatUtils.js'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectNoAppCrash,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'
import {
  apiRequest,
  deleteJointGroup,
  generateAndApproveThroughUi,
  seedEndedJointLesson,
  seedJointAcceptanceInputs,
} from '../utils/scheduler-fixtures.js'

const DAY_MS = 86_400_000
const addDays = (isoDate, days) => new Date(Date.parse(`${isoDate}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)

function thisWeekMonday() {
  const date = new Date()
  date.setHours(12, 0, 0, 0)
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
  return date.toISOString().slice(0, 10)
}

// The engine publishes only into periods that have not started. Find the first
// week whose teacher view carries a joint lesson naming both member classes.
async function firstJointPublishedWeek(page, horizon, classAName, classBName) {
  for (let weekStart = horizon.min_week_start; weekStart <= horizon.hard_end_date; weekStart = addDays(weekStart, 7)) {
    const rows = (await apiRequest(page, 'GET', `/schedule/week?week_start=${weekStart}`)).filter((row) => row.scheduler_lesson_id)
    const joint = rows.find((row) => {
      const names = (row.class_infos ?? []).map((item) => item.name ?? item.class_name)
      const others = (row.joint_classes ?? []).map((item) => item.name)
      return names.includes(classAName) && names.includes(classBName)
        || others.includes(classAName) && others.includes(classBName)
    })
    if (joint) return { weekStart, row: joint }
  }
  throw new Error('No published joint lesson was found for the teacher week view.')
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

// Class view on the admin Schedules page: the joint week is located through the
// read-only API, then the "Turma" view opens that exact week via ?weekStart.
async function firstClassJointWeek(page, classId, otherName) {
  let weekStart = thisWeekMonday()
  for (let attempt = 0; attempt < 16; attempt += 1) {
    const slots = await apiRequest(page, 'GET', `/schedule/week?class_id=${classId}&week_start=${weekStart}`)
    if (slots.some((slot) => (slot.joint_classes ?? []).some((cls) => cls.name === otherName))) return weekStart
    weekStart = addDays(weekStart, 7)
  }
  throw new Error('No published joint lesson was found for the class week view.')
}

async function openClassJointWeek(page, classId, className, otherName) {
  const weekStart = await firstClassJointWeek(page, classId, otherName)
  await goTo(page, `/schedules?weekStart=${weekStart}`)
  await page.getByRole('button', { name: 'Turma', exact: true }).click()
  await page.getByLabel('Turma', { exact: true }).selectOption({ label: className })
  await expect(
    page.getByRole('gridcell', { name: new RegExp(`em conjunto com ${otherName}`) }).first(),
  ).toBeVisible({ timeout: 30_000 })
}

// Monday of the week that contains an ISO date, in the same UTC arithmetic the
// rest of this file uses.
const weekStartOf = (isoDate) => addDays(isoDate, -((new Date(`${isoDate}T00:00:00Z`).getUTCDay() + 6) % 7))

const rowModuleIds = (row) => (row.slices ?? []).map((slice) => slice.module_id)
const isClassOnly = (row) => (row.joint_classes ?? []).length === 0

// The week API exposes the lesson end, not its start; derive the start from the
// slot interval so two lessons can be ordered on the same absolute scale.
const minutesBetween = (start, end) => {
  const [startHour, startMinute] = start.split(':').map(Number)
  const [endHour, endMinute] = end.split(':').map(Number)
  return (endHour * 60 + endMinute) - (startHour * 60 + startMinute)
}
const slotStartMs = (row) => Date.parse(row.ends_at) - minutesBetween(
  row.timeslot.start_time, row.timeslot.end_time,
) * 60_000

// Every published row of one class from the given week on. The deficit lesson
// and the next separate-module lesson can land in any later week.
async function classScheduleRows(page, classId, fromWeek, weeks = 12) {
  const rows = []
  for (let index = 0; index < weeks; index += 1) {
    const weekStart = addDays(fromWeek, index * 7)
    const slots = await apiRequest(page, 'GET', `/schedule/week?class_id=${classId}&week_start=${weekStart}`)
    rows.push(...slots.filter((row) => row.scheduler_lesson_id))
  }
  return rows
}

// The past week can share days with today's published lessons: match the joint
// block by its own date and interval before acting on it.
async function openHistoricalJointRecord(page, classAName, classBName, expectedDate, expectedInterval) {
  const grid = page.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
  const cells = grid.getByRole('gridcell', { name: new RegExp(`${classAName} \\+ ${classBName}`) })
  await expect(cells.first()).toBeVisible()
  for (const cell of await cells.all()) {
    await cell.getByRole('button').click()
    const dialog = page.getByRole('dialog')
    const text = await dialog.innerText()
    if (text.includes(expectedDate) && text.includes(expectedInterval)) return dialog
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  throw new Error('The historical joint lesson is not visible in the teacher week grid.')
}

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

// Manual acceptance (PR 5 steps 1–4) through the real UI: create a joint group
// of four shared modules with one separate module per class, confirm both
// members, the blocked shared module, the class weekly text and the single
// teacher block. It cleans only the joint group it created.
test.describe('Joint lessons — shared modules', () => {
  test('creates a four-module joint group and exposes it in both views', async ({ page, browser }) => {
    test.setTimeout(600_000)
    attachRuntimeGuards(page)
    allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
    await loginAsAdminReal(page)

    const joint = await seedJointAcceptanceInputs(page)
    const [classA, classB] = joint.classes

    // Manual step 1–2: create the joint group through the real modal. Class B
    // marks M1..M4 and M6; the four common modules are the only joint ones.
    await goTo(page, `/courses/${joint.courseId}/classes/${classA.id}/subjects`)
    await expectRouteReady(page, `/courses/${joint.courseId}/classes/${classA.id}/subjects`)
    const subjectCard = page.getByRole('list', { name: 'Disciplinas da turma' }).getByRole('listitem').filter({ hasText: 'E2E Joint Subject' })
    await subjectCard.getByRole('button', { name: /Dar em conjunto com/ }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('Aula conjunta · E2E Joint Subject')).toBeVisible()
    await dialog.getByLabel(new RegExp(classB.name)).check()
    const sharedLabels = ['E2E-J1', 'E2E-J2', 'E2E-J3', 'E2E-J4']
    for (const [index, code] of sharedLabels.entries()) {
      await expect(dialog.getByLabel(`${code} E2E Joint M${index + 1} · 2 h`)).toBeChecked()
    }
    await dialog.getByRole('button', { name: 'Criar junção', exact: true }).click()
    await expect(dialog).toBeHidden()

    // Manual step 3: both members show the joint summary.
    await expect(page.getByText(new RegExp(`Em conjunto com ${classB.name}`)).first()).toBeVisible()
    await expect(page.getByText(/Módulos E2E-J1, E2E-J2, E2E-J3, E2E-J4/)).toBeVisible()
    // The shared modules are locked in the checklist with the helper text.
    await subjectCard.getByRole('button', { name: 'Módulos: 5 de 6 · 10 h' }).click()
    await expect(subjectCard.getByLabel('E2E-J1 E2E Joint M1 · 2 h')).toBeDisabled()
    await expect(subjectCard.getByLabel('E2E-J5 E2E Joint M5 · 2 h')).toBeEnabled()
    await expect(subjectCard.getByText('Retire primeiro este módulo da aula conjunta.').first()).toBeVisible()

    await goTo(page, `/courses/${joint.courseId}/classes/${classB.id}/subjects`)
    await expect(page.getByText(new RegExp(`Em conjunto com ${classA.name}`)).first()).toBeVisible()

    // Manual step 4: generate and approve.
    await generateAndApproveThroughUi(page)

    // Class weekly view: the joint lesson names the other member class.
    await openClassJointWeek(page, classA.id, classA.name, classB.name)
    await expectNoAppCrash(page)

    // Teacher view: one block that names every member class.
    const teacherContext = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    let historyWeek
    let movedLesson
    let missedModuleIds
    let occurrenceId
    let debtsBefore
    try {
      const teacherPage = await teacherContext.newPage()
      attachRuntimeGuards(teacherPage)
      await loginAsTeacherReal(teacherPage)
      const horizon = await apiRequest(teacherPage, 'GET', '/schedule/me/horizon')
      const week = await firstJointPublishedWeek(teacherPage, horizon, classA.name, classB.name)
      await openTeacherWeek(teacherPage, horizon, week.weekStart)
      await expect(
        teacherPage
          .getByRole('table', { name: 'Grelha semanal de horários', exact: true })
          .getByRole('gridcell', { name: new RegExp(`${classA.name} \\+ ${classB.name}`) })
          .first(),
      ).toBeVisible({ timeout: 30_000 })
      await expectNoAppCrash(teacherPage)

      // Manual step 5: log the ended joint lesson with class B absent. The engine
      // never publishes into the past, so the fixture moves the first joint
      // lesson into an earlier week first.
      const history = await seedEndedJointLesson(page)
      historyWeek = weekStartOf(history.school_date)
      const historyRows = await apiRequest(teacherPage, 'GET', `/schedule/week?week_start=${historyWeek}`)
      movedLesson = historyRows.find((row) => history.lesson_ids.includes(row.scheduler_lesson_id))
      expect(movedLesson, 'the ended joint lesson should be published in the past week').toBeTruthy()
      missedModuleIds = new Set(rowModuleIds(movedLesson))
      debtsBefore = await apiRequest(page, 'GET', '/occurrences/debts')

      await openTeacherWeek(teacherPage, horizon, historyWeek)
      const interval = `${movedLesson.timeslot.start_time} – ${movedLesson.timeslot.end_time}`
      const logDialog = await openHistoricalJointRecord(
        teacherPage, classA.name, classB.name, formatDateLong(movedLesson.date), interval,
      )
      const presentB = logDialog.getByRole('checkbox', { name: classB.name, exact: true })
      await expect(presentB).toBeChecked()
      await presentB.uncheck()
      await expect(logDialog.getByText('A turma fica com uma ocorrência pendente. A direção decide a falta.')).toBeVisible()
      await logDialog.getByLabel('Sumário', { exact: true }).fill('CI: aula conjunta passada; a turma B faltou.')
      const saved = teacherPage.waitForResponse((response) => (
        new URL(response.url()).pathname === `/api/v1/schedule/lessons/${movedLesson.scheduler_lesson_id}/log`
        && response.request().method() === 'PUT'
      ))
      await logDialog.getByRole('button', { name: 'Aula Dada', exact: true }).click()
      const savedResponse = await saved
      expect(savedResponse.status()).toBe(200)
      expect(savedResponse.request().postDataJSON()).toMatchObject({
        status: 'COMPLETED',
        absent_class_ids: [classB.id],
      })
      const savedByClass = new Map((await savedResponse.json()).classes.map((row) => [row.class_id, row.status]))
      expect(savedByClass.get(classA.id)).toBe('COMPLETED')
      expect(savedByClass.get(classB.id)).toBe('OCCURRENCE')
      await expect(teacherPage.getByText('Registo guardado.', { exact: true })).toBeVisible()

      // The teacher grid collapses a joint lesson to one line, which can be the
      // present class. Read class B's own line to get its pending occurrence.
      const loggedRow = (await apiRequest(page, 'GET', `/schedule/week?class_id=${classB.id}&week_start=${historyWeek}`))
        .find((row) => history.lesson_ids.includes(row.scheduler_lesson_id))
      expect(loggedRow?.occurrence_id).toBeTruthy()
      occurrenceId = loggedRow.occurrence_id
      // A pending occurrence creates no debt and no execution before the decision.
      expect(await apiRequest(page, 'GET', `/occurrences/${occurrenceId}`)).toMatchObject({
        operational_state: 'OPEN_PENDING',
        decided_at: null,
      })
      expect((await apiRequest(page, 'GET', '/occurrences/debts')).total_hours_owed)
        .toBe(debtsBefore.total_hours_owed)
      await expectNoAppCrash(teacherPage)
    } finally {
      await teacherContext.close()
    }

    // Manual step 5 (administration): decide GAP for class B only, through the
    // per-class action on the joint occurrence card, and confirm class A is
    // untouched by a decision that is not a substitution.
    await goTo(page, `/absences?class_id=${classB.id}`)
    await expectRouteReady(page, '/absences')
    const beforeDecision = await apiRequest(page, 'GET', `/occurrences/${occurrenceId}`)
    const classBEntry = beforeDecision.joint_lesson.classes.find((row) => row.class_id === classB.id)
    expect(classBEntry, 'class B should carry its own occurrence row').toBeTruthy()
    const classAStateBefore = beforeDecision.joint_lesson.classes
      .find((row) => row.class_id === classA.id).operational_state
    const furoB = page.getByRole('button', { name: `Furo ${classB.name}`, exact: true })
    await expect(furoB).toBeVisible()
    const decided = page.waitForResponse((response) => (
      new URL(response.url()).pathname === `/api/v1/occurrences/${classBEntry.id}`
      && response.request().method() === 'PATCH'
    ))
    await furoB.click()
    const decidedResponse = await decided
    expect(decidedResponse.status()).toBe(200)
    expect(decidedResponse.request().postDataJSON()).toMatchObject({ status: 'GAP', class_ids: [classB.id] })
    await expect(page.getByText('Decisão registada.', { exact: true })).toBeVisible()

    const afterDecision = await apiRequest(page, 'GET', `/occurrences/${occurrenceId}`)
    expect(afterDecision).toMatchObject({
      status: 'GAP',
      operational_state: 'DECIDED_GAP',
      substitute_teacher_id: null,
      substitute_block_id: null,
    })
    expect(afterDecision.joint_lesson.classes.find((row) => row.class_id === classA.id).operational_state)
      .toBe(classAStateBefore)
    expect((await apiRequest(page, 'GET', '/occurrences/debts')).total_hours_owed)
      .toBeGreaterThan(debtsBefore.total_hours_owed)

    // Manual step 6: repair the schedule and confirm the deficit lesson only for
    // class B, before its next separate module.
    await generateAndApproveThroughUi(page)
    const rowsB = await classScheduleRows(page, classB.id, historyWeek)
    const deficitLesson = rowsB.find((row) => (
      isClassOnly(row) && rowModuleIds(row).some((moduleId) => missedModuleIds.has(moduleId))
    ))
    expect(deficitLesson, 'the repair should place class B deficit lesson for the missed shared module').toBeTruthy()
    const separateRows = rowsB.filter((row) => (
      isClassOnly(row) && rowModuleIds(row).includes(joint.separateModuleIds.b)
    ))
    expect(separateRows.length).toBeGreaterThan(0)
    const nextSeparate = separateRows.reduce((earliest, row) => (
      slotStartMs(row) < slotStartMs(earliest) ? row : earliest
    ))
    expect(Date.parse(deficitLesson.ends_at)).toBeLessThanOrEqual(slotStartMs(nextSeparate))

    const deficitWeek = weekStartOf(deficitLesson.date)
    const moduleName = deficitLesson.module.name
    await goTo(page, `/schedules?weekStart=${deficitWeek}`)
    await page.getByRole('button', { name: 'Turma', exact: true }).click()
    await page.getByLabel('Turma', { exact: true }).selectOption({ label: classB.name })
    const grid = page.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
    const deficitCell = grid.locator(`td[title*="Modulo: ${moduleName}"]:not([title*="${classA.name}"])`)
    await expect(deficitCell.first()).toBeVisible({ timeout: 30_000 })
    const deficitTitle = await deficitCell.first().getAttribute('title')
    expect(deficitTitle).toContain(classB.name)
    expect(deficitTitle).not.toContain(classA.name)
    await expect(deficitCell.first()).not.toContainText('em conjunto com')
    await expectNoAppCrash(page)

    // Class A never receives class B's deficit lesson.
    await page.getByLabel('Turma', { exact: true }).selectOption({ label: classA.name })
    await expect(grid.locator(`td[title*="Modulo: ${moduleName}"]:not([title*="${classB.name}"])`)).toHaveCount(0)
    const rowsA = await apiRequest(page, 'GET', `/schedule/week?class_id=${classA.id}&week_start=${deficitWeek}`)
    expect(rowsA.filter((row) => (
      isClassOnly(row) && rowModuleIds(row).some((moduleId) => missedModuleIds.has(moduleId))
    ))).toHaveLength(0)

    // A joint module already executed cannot leave the group (J19), so the undo
    // is refused; the disposable test stack removes the leftover group.
    allowApiFailure(page, { status: 409, url: '/api/v1/joint-lesson-groups/' })
    expect(await deleteJointGroup(page, classA.id)).toBe('started')
    await expectNoAppCrash(page)
  })
})
