import { createClerkClient } from '@clerk/backend'
import { test, expect } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  expectRouteReady,
  goTo,
} from '../utils/clerk-helpers.js'
import { apiRequest, seedMinimalSchedulerInputs } from '../utils/scheduler-fixtures.js'
import { cleanupFreshFounder, createFreshFounder } from '../utils/fresh-founder.js'

// This journey lives in the `app` Playwright project: the readiness folder is
// not part of `isolatedMatch` and the global grouping is left unchanged. Its
// data isolation comes from a fresh Clerk organization that the spec creates
// and deletes itself, so it never reads or writes the shared organization.
const SECOND_CLASS_NAME = 'E2E Availability Class B'

function nextSchoolDates() {
  const start = new Date()
  start.setHours(12, 0, 0, 0)
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7) + 7)
  const end = new Date(start)
  end.setDate(end.getDate() + 60)
  const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  return { schoolStartDate: iso(start), schoolHardEndDate: iso(end) }
}

// Fresh-organization onboarding, mirroring the proven founder flow, so this
// journey never touches the shared disposable E2E organization.
async function completeFoundation(page, dates) {
  await expect(page.locator('#school_start_date')).toBeEnabled({ timeout: 30_000 })
  await page.locator('#school_start_date').fill(dates.schoolStartDate)
  await page.locator('#school_hard_end_date').fill(dates.schoolHardEndDate)
  for (let step = 1; step < 8; step += 1) {
    await page.getByRole('button', { name: /seguinte/i }).click()
  }
  const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
  await expect(automaticHolidays).not.toBeChecked()
  const draftSaveResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/foundation/draft')
    && response.request().method() === 'PUT'
    && response.status() === 200
  ))
  await automaticHolidays.check()
  await draftSaveResponse
  await page.getByRole('button', { name: /seguinte/i }).click()
  await page.getByRole('button', { name: /ignorar por agora/i }).click()
  await page.locator('#foundation-confirmation').check()
  await page.getByRole('button', { name: /^ativar escola$/i }).click()
  await expectRouteReady(page, '/dashboard')
}

// A second class in the same course is the neutral source. Both classes share
// the fixture subject and the assigned teacher the prevalidation filter needs.
// The class-subject link uses the current API defaults: POST selects every
// module of the subject (D03) and the PATCH sets the teacher without clearing
// the selection.
async function createSecondClass(page, firstClass) {
  const courses = await apiRequest(page, 'GET', '/courses/')
  const course = courses.find((item) => item.name === 'E2E Dashboard Course')
  if (!course) throw new Error('Fixture course was not found for the class availability journey.')
  const payload = {
    name: SECOND_CLASS_NAME,
    size: 20,
    grade_level: firstClass.grade_level,
    start_year: firstClass.start_year,
    end_year: firstClass.end_year,
  }
  const courseDetail = await apiRequest(page, 'GET', `/courses/${course.id}`)
  const existing = courseDetail.classes.find((item) => item.name === SECOND_CLASS_NAME)
  const secondClass = existing
    ? await apiRequest(page, 'PATCH', `/courses/${course.id}/classes/${existing.id}`, payload)
    : await apiRequest(page, 'POST', `/courses/${course.id}/classes`, payload)

  const firstSubjects = await apiRequest(page, 'GET', `/classes/${firstClass.id}/subjects`)
  const linked = firstSubjects.subjects.find((item) => item.teacher_id)
  if (!linked) throw new Error('The fixture class has no subject assigned to a teacher.')
  await apiRequest(page, 'POST', `/classes/${secondClass.id}/subjects`, { subject_id: linked.subject_id })
  await apiRequest(page, 'PATCH', `/classes/${secondClass.id}/subjects/${linked.subject_id}`, {
    teacher_id: linked.teacher_id,
  })
  return { courseId: course.id, secondClass }
}

async function markEveryBlockImpossible(page) {
  await page.getByRole('button', { name: 'Impossível', exact: true }).click()
  const cells = page.locator('.availability-grid__cell')
  const total = await cells.count()
  for (let index = 0; index < total; index += 1) {
    await cells.nth(index).click()
  }
  await page.getByRole('button', { name: /guardar disponibilidade/i }).click()
  await expect(page.getByText(/Disponibilidade da turma guardada/)).toBeVisible({ timeout: 30_000 })
}

function blockerLink(page, className) {
  return page.getByRole('link', { name: new RegExp(`${className} tem todos os blocos`) })
}

// The grid endpoint returns one entry per visible block, so a saved grid is
// proven by checking every score, never by a single sample.
function expectEveryGridScore(grid, score) {
  expect(grid.length).toBeGreaterThan(0)
  for (const item of grid) expect(item.score).toBe(score)
}

test.describe.configure({ mode: 'serial' })

test('an all-impossible class blocks generation until a neutral grid is copied onto it', async ({ page }) => {
  test.setTimeout(600_000)

  attachRuntimeGuards(page)
  allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for the class availability journey.')
  const client = createClerkClient({ secretKey })

  let founder
  let primaryError = null
  let cleanupError = null

  try {
    founder = await createFreshFounder(page, client, 'Class Availability')
    await completeFoundation(page, nextSchoolDates())

    const firstClass = await seedMinimalSchedulerInputs(page, founder.email)
    const { courseId, secondClass } = await createSecondClass(page, firstClass)

    await test.step('marks every block of the class as impossible', async () => {
      await goTo(page, `/courses/${courseId}/classes/${firstClass.id}`)
      await expect(page.getByText('Disponibilidade')).toBeVisible({ timeout: 30_000 })
      await page.getByRole('button', { name: /editar disponibilidade/i }).click()
      await expect(page.getByText(`Disponibilidade — ${firstClass.name}`)).toBeVisible()
      await markEveryBlockImpossible(page)
      await expect(page.getByText(/Não é possível colocar|Sem restrições/)).toHaveCount(0)
      await page.getByRole('button', { name: 'Fechar', exact: true }).click()
      await expect(page.getByText('Disponibilidade')).toBeVisible()
    })

    await test.step('blocks the generation in the prevalidation', async () => {
      await goTo(page, '/schedules')
      await expectRouteReady(page, '/schedules')
      await expect(blockerLink(page, firstClass.name)).toBeVisible({ timeout: 30_000 })
    })

    await test.step('copies a neutral grid onto the blocked class through the editor', async () => {
      const blockedGrid = await apiRequest(page, 'GET', `/classes/${firstClass.id}/availability`)
      expectEveryGridScore(blockedGrid, -1)
      const sourceGrid = await apiRequest(page, 'GET', `/classes/${secondClass.id}/availability`)
      expectEveryGridScore(sourceGrid, 1)

      await goTo(page, `/courses/${courseId}/classes/${secondClass.id}`)
      await page.getByRole('button', { name: /editar disponibilidade/i }).click()
      await expect(page.getByText(`Disponibilidade — ${secondClass.name}`)).toBeVisible()
      await page.getByRole('button', { name: /aplicar a outras turmas/i }).click()
      await page.getByRole('checkbox', { name: firstClass.name, exact: true }).check()
      await page.getByRole('button', { name: 'Aplicar a 1 turmas', exact: true }).click()
      const confirmation = page.getByRole('dialog').filter({ hasText: 'Vai substituir' })
      await confirmation.getByRole('button', { name: 'Aplicar', exact: true }).click()
      await expect(page.getByText(/Disponibilidade aplicada a 1 turmas/)).toBeVisible({ timeout: 30_000 })

      const copiedGrid = await apiRequest(page, 'GET', `/classes/${firstClass.id}/availability`)
      expect(copiedGrid).toEqual(sourceGrid)
      const untouchedGrid = await apiRequest(page, 'GET', `/classes/${secondClass.id}/availability`)
      expect(untouchedGrid).toEqual(sourceGrid)
      await page.getByRole('button', { name: 'Fechar', exact: true }).click()
    })

    await test.step('generation is no longer blocked by that class', async () => {
      await goTo(page, '/schedules')
      await expectRouteReady(page, '/schedules')
      await expect(blockerLink(page, firstClass.name)).toHaveCount(0)
    })
  } catch (error) {
    primaryError = error
  } finally {
    if (founder) {
      try {
        await cleanupFreshFounder(client, founder)
      } catch (error) {
        cleanupError = error
      }
    }
  }

  if (primaryError) {
    if (cleanupError) console.error('Cleanup failed after the primary E2E error:', cleanupError)
    throw primaryError
  }
  if (cleanupError) throw cleanupError
})
