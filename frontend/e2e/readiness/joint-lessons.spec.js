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
  seedJointLessonInputs,
} from '../utils/scheduler-fixtures.js'

const DAY_MS = 86_400_000
const addDays = (isoDate, days) => new Date(Date.parse(`${isoDate}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)

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

test.describe.configure({ mode: 'serial' })
test.use({ storageState: '.auth/admin.json' })

// A joint lesson shares some modules of a subject between two classes with one
// teacher, one room and one time. This journey seeds its own fixtures, creates
// the group through the real modal, generates and approves, and checks the
// single teacher-view block. It cleans only the joint group it created.
test.describe('Joint lessons — shared modules', () => {
  test('creates a joint group through the modal and shows one teacher block', async ({ page, browser }) => {
    test.setTimeout(600_000)
    attachRuntimeGuards(page)
    allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
    await loginAsAdminReal(page)

    const joint = await seedJointLessonInputs(page)
    const [classA, classB] = joint.classes

    await goTo(page, `/courses/${joint.courseId}/classes/${classA.id}/subjects`)
    await expectRouteReady(page, `/courses/${joint.courseId}/classes/${classA.id}/subjects`)

    // Create the joint group through the real modal.
    const subjectCard = page.locator('.card', { hasText: 'E2E Joint Subject' }).first()
    await subjectCard.getByRole('button', { name: /Dar em conjunto com/ }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('Aula conjunta · E2E Joint Subject')).toBeVisible()
    await dialog.getByLabel(new RegExp(classB.name)).check()
    await dialog.getByRole('button', { name: 'Criar junção', exact: true }).click()
    await expect(dialog).toBeHidden()

    await expect(page.getByText(new RegExp(`Em conjunto com ${classB.name}`)).first()).toBeVisible()

    // The other member class shows the same joint.
    await goTo(page, `/courses/${joint.courseId}/classes/${classB.id}/subjects`)
    await expect(page.getByText(new RegExp(`Em conjunto com ${classA.name}`)).first()).toBeVisible()

    await generateAndApproveThroughUi(page)

    // Teacher view: one block that names every member class.
    // The teacher needs a signed-out context: this test loads the admin
    // session, and browser.newContext() would otherwise inherit it.
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
