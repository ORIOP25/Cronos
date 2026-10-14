import { expect, test } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'
import {
  apiRequest,
  generateAndApproveThroughUi,
  seedMinimalSchedulerInputs,
} from '../utils/scheduler-fixtures.js'

test.use({ storageState: '.auth/admin.json' })

const PREVALIDATION_URL = '/api/v1/readiness/prevalidation'
const SUBJECT_NAME = 'E2E Module Selection Subject'
const MODULE_NAMES = ['E2E Selection Module A', 'E2E Selection Module B']
const CLASS_NAME = 'E2E Module Selection Class'

// The shared `E2E Dashboard Subject` keeps a single module so other journeys
// are untouched; this spec owns a dedicated two-module subject and class.
async function ensureTwoModuleSubject(page) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  const existing = subjects.find((subject) => subject.name === SUBJECT_NAME)
  const existingByName = new Map((existing?.modules || []).map((module) => [module.name, module]))
  const modules = MODULE_NAMES.map((name, order) => ({
    ...(existingByName.get(name)?.id ? { id: existingByName.get(name).id } : {}),
    name,
    code: `E2E-SEL-${order + 1}`,
    hours_total: 2,
    order,
  }))
  const payload = { name: SUBJECT_NAME, required_room_type: 'normal', modules }
  return existing
    ? apiRequest(page, 'PATCH', `/subjects/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/subjects/', payload)
}

async function ensureSelectionClass(page, courseId, baseClass) {
  const course = await apiRequest(page, 'GET', `/courses/${courseId}`)
  const existing = course.classes.find((classroom) => classroom.name === CLASS_NAME)
  const payload = {
    name: CLASS_NAME,
    size: 20,
    grade_level: baseClass.grade_level,
    start_year: baseClass.start_year,
    end_year: baseClass.end_year,
  }
  return existing
    ? apiRequest(page, 'PATCH', `/courses/${courseId}/classes/${existing.id}`, payload)
    : apiRequest(page, 'POST', `/courses/${courseId}/classes`, payload)
}

async function grantTeacherCompetency(page, subjectId) {
  const email = process.env.E2E_CLERK_TEACHER_EMAIL
  const members = await apiRequest(page, 'GET', '/members')
  const member = members.items.find((item) => item.email.toLowerCase() === email.toLowerCase())
  if (!member) throw new Error(`Prepared E2E teacher member not found: ${email}`)
  const capabilities = Array.from(new Set([...member.capabilities, 'teacher']))
  return apiRequest(page, 'PATCH', `/members/${member.id}`, {
    capabilities,
    teacher_access_mode: capabilities.includes('admin')
      ? 'platform'
      : member.teacher_access_mode || 'scheduler_only',
    subject_ids: Array.from(new Set([...(member.subject_ids || []), subjectId])),
    lock_version: member.lock_version,
  })
}

async function linkSubjectWithTeacher(page, classId, subjectId, teacherId) {
  let classSubjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  if (!classSubjects.subjects.some((link) => link.subject_id === subjectId)) {
    await apiRequest(page, 'POST', `/classes/${classId}/subjects`, { subject_id: subjectId })
  }
  classSubjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  const link = classSubjects.subjects.find((item) => item.subject_id === subjectId)
  await apiRequest(page, 'PATCH', `/classes/${classId}/subjects/${subjectId}`, {
    teacher_id: teacherId,
    module_ids: link.modules.map((module) => module.id),
  })
  return link
}

// Scans every published week of the year and collects the module ids that the
// class's scheduled lessons actually reference. Fresh fixture, so no history.
async function collectClassSliceModuleIds(page, classId) {
  const monday = new Date()
  monday.setHours(12, 0, 0, 0)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  const moduleIds = new Set()
  for (let week = 0; week < 10; week += 1) {
    const start = new Date(monday)
    start.setDate(start.getDate() + week * 7)
    const slots = await apiRequest(
      page,
      'GET',
      `/schedule/week?class_id=${classId}&week_start=${start.toISOString().slice(0, 10)}`,
    )
    for (const slot of slots) {
      for (const slice of slot.slices || []) moduleIds.add(slice.module_id)
    }
  }
  return moduleIds
}

test.describe('Readiness — per-class module selection', () => {
  test('keeps the omitted module out of the generated schedule', async ({ page }) => {
    test.setTimeout(300_000)

    attachRuntimeGuards(page)
    allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
    await loginAsAdminReal(page)
    await goTo(page, '/dashboard')

    const baseClass = await seedMinimalSchedulerInputs(page)
    const subject = await ensureTwoModuleSubject(page)
    const selectionClass = await ensureSelectionClass(page, baseClass.course_id, baseClass)
    const teacher = await grantTeacherCompetency(page, subject.id)
    const link = await linkSubjectWithTeacher(page, selectionClass.id, subject.id, teacher.teacher_id)

    const subjectsPath = `/courses/${selectionClass.course_id}/classes/${selectionClass.id}/subjects`
    const moduleByName = new Map(link.modules.map((module) => [module.name, module]))
    const moduleA = moduleByName.get(MODULE_NAMES[0])
    const moduleB = moduleByName.get(MODULE_NAMES[1])
    expect(moduleA && moduleB).toBeTruthy()

    try {
      await goTo(page, subjectsPath)
      const expand = page.getByRole('button', { name: 'Módulos: 2 de 2 · 4 h' })
      await expect(expand).toBeVisible()
      await expand.click()

      const checkA = page.getByRole('checkbox', { name: new RegExp(MODULE_NAMES[0]) })
      const checkB = page.getByRole('checkbox', { name: new RegExp(MODULE_NAMES[1]) })
      await expect(checkA).toBeChecked()
      await expect(checkB).toBeChecked()

      // Manual step: deselect one module and check the counter.
      let save = page.waitForResponse((response) => (
        response.url().includes(`/api/v1/classes/${selectionClass.id}/subjects/`)
        && response.request().method() === 'PATCH'
      ))
      await checkB.uncheck()
      expect((await save).ok()).toBeTruthy()
      await expect(page.getByRole('button', { name: 'Módulos: 1 de 2 · 2 h' })).toBeVisible()

      // Manual step: deselect every module and confirm the prevalidation block.
      save = page.waitForResponse((response) => (
        response.url().includes(`/api/v1/classes/${selectionClass.id}/subjects/`)
        && response.request().method() === 'PATCH'
      ))
      await checkA.uncheck()
      expect((await save).ok()).toBeTruthy()
      await expect(page.getByRole('button', { name: 'Módulos: 0 de 2 · 0 h' })).toBeVisible()
      await expect(page.locator('span.text-warning', { hasText: 'Sem módulos' })).toBeVisible()

      const blockedPrevalidation = page.waitForResponse((response) => (
        response.url().includes(PREVALIDATION_URL) && response.request().method() === 'GET'
      ), { timeout: 30_000 })
      await goTo(page, '/schedules')
      const blockedReport = await (await blockedPrevalidation).json()
      expect(
        blockedReport.issues
          .filter((issue) => issue.route === subjectsPath)
          .map((issue) => issue.code),
      ).toContain('CLASS_SUBJECT_WITHOUT_MODULES')
      await expect(page.locator(`.alert a[href="${subjectsPath}"]`))
        .toContainText(/sem módulos selecionados/i)

      // Manual step: reselect one module, then generate and approve.
      await goTo(page, subjectsPath)
      await page.getByRole('button', { name: 'Módulos: 0 de 2 · 0 h' }).click()
      save = page.waitForResponse((response) => (
        response.url().includes(`/api/v1/classes/${selectionClass.id}/subjects/`)
        && response.request().method() === 'PATCH'
      ))
      await page.getByRole('checkbox', { name: new RegExp(MODULE_NAMES[0]) }).check()
      expect((await save).ok()).toBeTruthy()
      await expect(page.getByRole('button', { name: 'Módulos: 1 de 2 · 2 h' })).toBeVisible()

      await generateAndApproveThroughUi(page)

      const plannedModuleIds = await collectClassSliceModuleIds(page, selectionClass.id)
      expect(plannedModuleIds.has(moduleA.id)).toBe(true)
      expect(plannedModuleIds.has(moduleB.id)).toBe(false)
    } finally {
      // Restore this dedicated class subject even when the journey fails, so a
      // zero-module selection never blocks generation for the tests after it.
      await apiRequest(page, 'PATCH', `/classes/${selectionClass.id}/subjects/${subject.id}`, {
        module_ids: [moduleA.id],
      })
    }
  })
})
