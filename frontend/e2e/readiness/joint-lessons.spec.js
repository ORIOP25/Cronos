import { expect, test } from '@playwright/test'
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
  generateAndApproveThroughUi,
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
    const subjectCard = page.locator('.card', { hasText: 'E2E Joint Subject' }).first()
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
    } finally {
      await teacherContext.close()
    }

    // Cleanup only the joint group created by this journey.
    const subjects = await apiRequest(page, 'GET', `/classes/${classA.id}/subjects`)
    const groupId = subjects.subjects.find((subject) => subject.joint_group)?.joint_group?.id
    if (groupId) {
      await apiRequest(page, 'DELETE', `/joint-lesson-groups/${groupId}`)
    }
    await expectNoAppCrash(page)
  })
})
