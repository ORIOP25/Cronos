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

const TEACHER_AVAILABILITY_LABEL = 'Disponibilidade dos professores'
const TEACHER_AVAILABILITY_CAPTION = 'Disponibilidade dos professores por professor'
const NEUTRAL_SCORE = 1
const IMPOSSIBLE_SCORE = -1

function uniqueSuffix() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

// A scheduler-only teacher never receives a Clerk invitation, so this fixture
// stays inside the disposable organization the journey already owns.
async function createSchedulerOnlyTeacher(page, name, email) {
  const member = await apiRequest(page, 'POST', '/members', {
    organization_display_name: name,
    email,
    capabilities: ['teacher'],
    teacher_access_mode: 'scheduler_only',
    subject_ids: [],
  })
  if (!member.teacher_id) throw new Error(`Scheduler-only teacher ${email} has no teacher_id.`)
  return member.teacher_id
}

// The downloaded teacher model is a plain CSV: BOM, semicolon delimiter, CRLF.
// Edit the first day of the target teacher so the preview reports one change.
// Native parsing only; the fixture values are simple.
function editTeacherBlock(csvText, email, level) {
  const lines = csvText.replace(/^\ufeff/, '').split('\r\n').filter((line) => line.length > 0)
  if (lines.length < 2) throw new Error('The downloaded teacher model has no teacher rows.')
  let edited = false
  const updated = lines.map((line, index) => {
    if (index === 0) return line
    const cells = line.split(';')
    if (!edited && cells[1]?.toLowerCase() === email.toLowerCase()) {
      if (cells.length < 4) throw new Error('The downloaded teacher row has no hour columns.')
      cells[3] = level
      edited = true
    }
    return cells.join(';')
  })
  if (!edited) throw new Error(`Teacher ${email} was not found in the downloaded model.`)
  return `\ufeff${updated.join('\r\n')}\r\n`
}

// Reads one teacher grid through the real API and proves the imported levels:
// exactly one blocked block and every other visible block neutral.
function expectOneImpossibleBlock(grid) {
  expect(grid.length).toBeGreaterThan(0)
  expect(grid.filter((item) => item.score === IMPOSSIBLE_SCORE)).toHaveLength(1)
  for (const item of grid) {
    expect([NEUTRAL_SCORE, IMPOSSIBLE_SCORE]).toContain(item.score)
  }
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
      await expect(page.getByText('Disponibilidade', { exact: true })).toBeVisible({ timeout: 30_000 })
      await page.getByRole('button', { name: /editar disponibilidade/i }).click()
      await expect(page.getByText(`Disponibilidade — ${firstClass.name}`, { exact: true })).toBeVisible()
      await markEveryBlockImpossible(page)
      await expect(page.getByText(/\d+ impossíveis/)).toBeVisible()
      await page.getByRole('button', { name: 'Fechar', exact: true }).click()
      await expect(page.getByText('Disponibilidade', { exact: true })).toBeVisible()
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
      await expect(page.getByText(`Disponibilidade — ${secondClass.name}`, { exact: true })).toBeVisible()
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

    await test.step('imports an edited teacher availability model through the real screens', async () => {
      const suffix = uniqueSuffix()
      const targets = [
        { name: 'E2E Availability A', email: `e2e-avail-a-${suffix}@example.com` },
        { name: 'E2E Availability B', email: `e2e-avail-b-${suffix}@example.com` },
      ]
      for (const target of targets) {
        target.teacherId = await createSchedulerOnlyTeacher(page, target.name, target.email)
      }

      await goTo(page, '/imports')
      await expect(page.getByRole('heading', { name: 'Importar dados' })).toBeVisible({ timeout: 30_000 })

      const downloadPromise = page.waitForEvent('download')
      await page
        .locator('.card')
        .filter({ hasText: TEACHER_AVAILABILITY_LABEL })
        .getByRole('button', { name: 'Descarregar modelo' })
        .click()
      const download = await downloadPromise
      const chunks = []
      for await (const chunk of await download.createReadStream()) chunks.push(chunk)
      let model = Buffer.concat(chunks).toString('utf8')
      for (const target of targets) model = editTeacherBlock(model, target.email, 'Impossível')

      await page.locator('#import-teacher_availability').setInputFiles({
        name: 'Cronos_DisponibilidadeProfessores_Template.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(model, 'utf8'),
      })

      const validateResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/imports/validate')
        && response.request().method() === 'POST'
      ))
      await page.getByRole('button', { name: 'Verificar ficheiros' }).click()
      const validation = await validateResponse
      expect(validation.ok(), `import validation failed: ${validation.status()}`).toBeTruthy()

      const teacherTable = page.locator('table').filter({ hasText: TEACHER_AVAILABILITY_CAPTION })
      await expect(teacherTable).toBeVisible({ timeout: 30_000 })
      for (const target of targets) {
        const row = teacherTable.locator('tbody tr').filter({ hasText: target.email })
        await expect(row).toHaveCount(1)
        await expect(row.locator('td').nth(0)).toHaveText(target.name)
        await expect(row.locator('td').nth(1)).toHaveText(target.email)
        await expect(row.locator('td').nth(2)).toHaveText('1')
      }

      const commitResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/imports/commit')
        && response.request().method() === 'POST'
      ))
      await page.getByRole('button', { name: 'Confirmar importação' }).click()
      const commit = await commitResponse
      expect(commit.ok(), `import commit failed: ${commit.status()}`).toBeTruthy()
      await expect(page.getByText('Importação concluída.')).toBeVisible({ timeout: 30_000 })

      for (const target of targets) {
        const grid = await apiRequest(page, 'GET', `/teachers/${target.teacherId}/availability`)
        expectOneImpossibleBlock(grid)
      }
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
