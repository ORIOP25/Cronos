import { createClerkClient } from '@clerk/backend'
import { clerk } from '@clerk/testing/playwright'
import { createPageObjects } from '@clerk/testing/playwright/unstable'
import { test, expect } from '@playwright/test'
import {
  allowApiFailure,
  attachRuntimeGuards,
  CLERK_LEGAL_UNSAFE_METADATA,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'
import {
  firstPublishedFutureSlot,
  waitForJobToSucceed as waitForSchedulerJob,
} from '../utils/scheduler-fixtures.js'
import { createE2eRunKey, E2E_BASE_URL } from '../utils/e2e-config.js'
import { cleanupOrganizationByName } from '../utils/fresh-founder.js'

const API_PREFIX = '/api/v1'
const OPERATION_TIMEOUT_MS = 30_000
const COMPOSED_FLOW_TIMEOUT_MS = 600_000

function withTimeout(operation, label, timeoutMs = OPERATION_TIMEOUT_MS) {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`${label} timed out after ${timeoutMs}ms`))
    }, timeoutMs)
  })
  return Promise.race([Promise.resolve().then(operation), timeout]).finally(() => {
    clearTimeout(timeoutId)
  })
}

function toIsoDate(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function schedulerFixtureDates(weekOffset) {
  const schoolStart = new Date()
  schoolStart.setHours(12, 0, 0, 0)
  const daysSinceMonday = (schoolStart.getDay() + 6) % 7
  schoolStart.setDate(schoolStart.getDate() - daysSinceMonday + (weekOffset * 7))
  const hardEnd = new Date(schoolStart)
  hardEnd.setDate(hardEnd.getDate() + 60)
  return {
    schoolStartDate: toIsoDate(schoolStart),
    schoolHardEndDate: toIsoDate(hardEnd),
    startYear: schoolStart.getFullYear(),
    endYear: Math.max(hardEnd.getFullYear(), schoolStart.getFullYear() + 1),
  }
}

// The engine never publishes into periods that already started, so the
// scenario starts on the next Monday and queries a week with real lessons.
const FIXTURE_DATES = schedulerFixtureDates(1)
const FRESH_FOUNDER_DATES = schedulerFixtureDates(1)
const FIXTURE = {
  subjectName: 'E2E Scheduler Subject',
  moduleName: 'E2E Scheduler Module',
  moduleCode: 'E2E-SCHED-1',
  courseName: 'E2E Scheduler Course',
  courseAbbreviation: 'E2ESCH',
  className: 'E2E Scheduler Class',
  roomName: 'E2E Scheduler Room',
  ...FIXTURE_DATES,
}

export async function apiRequest(page, method, path, body, timeoutMs = OPERATION_TIMEOUT_MS) {
  return await page.evaluate(
    async ({ apiPrefix, method: requestMethod, path: requestPath, body: requestBody, timeoutMs }) => {
      let token = null
      const organizationId = window.Clerk?.organization?.id ?? null
      const tokenOptions = organizationId ? { organizationId } : undefined
      try {
        token = await window.Clerk?.session?.getToken?.(tokenOptions)
      } catch {
        token = null
      }
      if (!token) {
        try {
          const activeSession = window.Clerk?.client?.sessions?.find(
            (session) => session.status === 'active',
          ) || window.Clerk?.client?.sessions?.[0]
          token = await activeSession?.getToken?.(tokenOptions)
        } catch {
          token = null
        }
      }
      const headers = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
      let response
      try {
        response = await fetch(`${apiPrefix}${requestPath}`, {
          method: requestMethod,
          credentials: 'same-origin',
          headers,
          body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
          signal: controller.signal,
        })
        const text = await response.text()
        let data = null
        try {
          data = text ? JSON.parse(text) : null
        } catch {
          data = text
        }
        if (!response.ok) {
          const currentOrganizationId = window.Clerk?.organization?.id ?? '<none>'
          throw new Error(
            `${requestMethod} ${requestPath} failed for organization ${currentOrganizationId}: `
            + `${response.status} ${text}`,
          )
        }
        return data
      } catch (error) {
        if (error?.name === 'AbortError') {
          throw new Error(`${requestMethod} ${requestPath} timed out after ${timeoutMs}ms`)
        }
        throw error
      } finally {
        clearTimeout(timeoutId)
      }
    },
    { apiPrefix: API_PREFIX, method, path, body, timeoutMs },
  )
}

async function rejectPendingDraftIfPresent(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.pending_proposal?.proposal_id) {
    await apiRequest(page, 'POST', `/scheduler/drafts/${status.pending_proposal.proposal_id}/reject`)
  }
}

async function clearExistingSchedulerFixture(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.school_year?.id) {
    await apiRequest(page, 'POST', '/school/settings/soft-reset', {
      confirm_phrase: 'Confirmo',
    })
  }
}

async function signInUserWithTicket(
  client,
  page,
  userId,
  path,
  { organizationName } = {},
) {
  const ticket = await withTimeout(
    () => client.signInTokens.createSignInToken({ userId, expiresInSeconds: 300 }),
    'Clerk sign-in token creation',
  )
  const baseUrl = E2E_BASE_URL
  const targetUrl = new URL(path, baseUrl)
  const ticketUrl = new URL(ticket.url)
  ticketUrl.searchParams.set('redirect_url', targetUrl.toString())
  await page.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })
  if (organizationName) {
    await page.waitForURL(/\/tasks\/choose-organization(?:[/?#]|$)/, { timeout: 30_000 })
    const clerkPages = createPageObjects({ page, baseURL: baseUrl })
    await withTimeout(
      () => clerkPages.sessionTask.resolveForceOrganizationSelectionTask({ name: organizationName }),
      'Clerk organization selection',
    )
  }
  if (organizationName) {
    await page.waitForURL('**/foundation', { timeout: 30_000 })
  } else {
    await page.waitForURL(targetUrl.toString(), { timeout: 30_000 })
  }
  await page.waitForFunction(() => window.Clerk?.user != null, null, { timeout: 30_000 })
  if (!organizationName) await expectRouteReady(page, path)
  if (organizationName) {
    return await page.evaluate((name) => (
      window.Clerk?.user?.organizationMemberships.find(
        (membership) => membership.organization.name === name,
      )?.organization.id ?? null
    ), organizationName)
  }
  return null
}

async function findPreparedTeacherMember(page, requestedEmail) {
  const teacherEmail = requestedEmail || process.env.E2E_CLERK_TEACHER_EMAIL
  if (!teacherEmail) {
    throw new Error('E2E_CLERK_TEACHER_EMAIL is required for scheduler E2E.')
  }

  const members = await apiRequest(page, 'GET', '/members')
  const teacher = members.items.find(
    (member) => member.email.toLowerCase() === teacherEmail.toLowerCase(),
  )
  if (!teacher) {
    throw new Error(`Prepared E2E teacher member not found: ${teacherEmail}`)
  }
  return teacher
}

function singleFixtureModule(existingSubject) {
  const existingModule = existingSubject?.modules?.[0]
  return {
    ...(existingModule?.id ? { id: existingModule.id } : {}),
    name: FIXTURE.moduleName,
    code: FIXTURE.moduleCode,
    hours_total: 2,
    order: 0,
  }
}

async function ensureFixtureSubject(page) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  const existing = subjects.find((subject) => subject.name === FIXTURE.subjectName)
  const payload = {
    name: FIXTURE.subjectName,
    required_room_type: 'normal',
    modules: [singleFixtureModule(existing)],
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/subjects/', payload)
  }
  return await apiRequest(page, 'PATCH', `/subjects/${existing.id}`, payload)
}

async function ensureFixtureCourse(page, subjectId) {
  const courses = await apiRequest(page, 'GET', '/courses/')
  const existing = courses.find((course) => course.name === FIXTURE.courseName)
  const payload = {
    name: FIXTURE.courseName,
    abbreviation: FIXTURE.courseAbbreviation,
    subject_ids: [subjectId],
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/courses/', {
      ...payload,
      teacher_assignments: [],
      classes_config: [],
    })
  }
  return await apiRequest(page, 'PATCH', `/courses/${existing.id}`, payload)
}

async function ensureFixtureClass(page, courseId, dates) {
  const course = await apiRequest(page, 'GET', `/courses/${courseId}`)
  const existing = course.classes.find((classroom) => classroom.name === FIXTURE.className)
  const payload = {
    name: FIXTURE.className,
    size: 20,
    grade_level: 10,
    start_year: dates.startYear,
    end_year: dates.endYear,
  }
  if (!existing) {
    return await apiRequest(page, 'POST', `/courses/${courseId}/classes`, payload)
  }
  return await apiRequest(page, 'PATCH', `/courses/${courseId}/classes/${existing.id}`, payload)
}

async function ensureFixtureRoom(page) {
  const rooms = await apiRequest(page, 'GET', '/rooms/')
  const existing = rooms.find((room) => room.name === FIXTURE.roomName)
  const payload = {
    name: FIXTURE.roomName,
    type: 'normal',
    capacity: 30,
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/rooms/', payload)
  }
  return await apiRequest(page, 'PATCH', `/rooms/${existing.id}`, payload)
}

async function ensureFixtureClassSubject(page, classroomId, subjectId, teacherId) {
  let classSubjects = await apiRequest(page, 'GET', `/classes/${classroomId}/subjects`)
  const hasFixtureSubject = classSubjects.subjects.some(
    (subject) => subject.subject_id === subjectId,
  )
  if (!hasFixtureSubject) {
    await apiRequest(page, 'POST', `/classes/${classroomId}/subjects`, { subject_id: subjectId })
  }

  classSubjects = await apiRequest(page, 'GET', `/classes/${classroomId}/subjects`)
  for (const subject of classSubjects.subjects) {
    if (subject.subject_id !== subjectId) {
      await apiRequest(page, 'DELETE', `/classes/${classroomId}/subjects/${subject.subject_id}`)
    }
  }

  classSubjects = await apiRequest(page, 'GET', `/classes/${classroomId}/subjects`)
  if (!classSubjects.subjects.some((subject) => subject.subject_id === subjectId)) {
    throw new Error(`Fixture subject ${subjectId} was not associated with class ${classroomId}.`)
  }
  await apiRequest(page, 'PATCH', `/classes/${classroomId}/subjects/${subjectId}`, {
    teacher_id: teacherId,
  })
}

async function e2eSubjectIds(page, fixtureSubjectId) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  return subjects
    .filter((subject) => (
      subject.id === fixtureSubjectId
      || subject.name === FIXTURE.subjectName
      || subject.name.startsWith('E2E Horario ')
    ))
    .map((subject) => subject.id)
}

export async function seedMinimalSchedulerInputs(page, teacherEmail, dates = FIXTURE_DATES) {
  await clearExistingSchedulerFixture(page)
  await rejectPendingDraftIfPresent(page)

  const subject = await ensureFixtureSubject(page)

  const teacherMember = await findPreparedTeacherMember(page, teacherEmail)
  const competencySubjectIds = Array.from(new Set([
    ...(teacherMember.subject_ids || []),
    ...(await e2eSubjectIds(page, subject.id)),
  ]))
  const capabilities = Array.from(new Set([...teacherMember.capabilities, 'teacher']))
  const updatedTeacher = await apiRequest(page, 'PATCH', `/members/${teacherMember.id}`, {
    capabilities,
    teacher_access_mode: capabilities.includes('admin')
      ? 'platform'
      : teacherMember.teacher_access_mode || 'scheduler_only',
    subject_ids: competencySubjectIds,
    lock_version: teacherMember.lock_version,
  })
  if (!updatedTeacher.teacher_id) {
    throw new Error('Prepared E2E teacher did not expose a teacher_id after subject assignment.')
  }

  const eligibleTeachers = await apiRequest(
    page,
    'GET',
    `/classes/subjects/${subject.id}/eligible-teachers`,
  )
  if (!eligibleTeachers.some((teacher) => teacher.id === updatedTeacher.teacher_id)) {
    throw new Error(
      `Teacher ${updatedTeacher.teacher_id} was not eligible for subject ${subject.id} after competency update.`,
    )
  }

  await apiRequest(page, 'POST', '/school/settings/', {
    school_start_date: dates.schoolStartDate,
    school_hard_end_date: dates.schoolHardEndDate,
    preferred_end_date: dates.schoolHardEndDate,
    repair_stability_window_days: 0,
  })
  await apiRequest(page, 'POST', '/school/grid-settings/regenerate', {
    grid_settings: {
      lunch_window_start: '12:30',
      lunch_window_end: '14:00',
      lunch_min_duration_minutes: 60,
    },
    timeslots: {
      start_time: '09:00',
      end_time: '14:00',
      slot_duration_minutes: 60,
      break_duration_minutes: 0,
      days_of_week: [0, 1, 2, 3, 4],
    },
  })
  await ensureFixtureRoom(page)
  const course = await ensureFixtureCourse(page, subject.id)
  const classroom = await ensureFixtureClass(page, course.id, dates)
  await ensureFixtureClassSubject(page, classroom.id, subject.id, updatedTeacher.teacher_id)

  return { classId: classroom.id, subjectId: subject.id, teacherId: updatedTeacher.teacher_id }
}

export async function generateAndApproveThroughUi(page) {
  await goTo(page, '/schedules')
  await expectRouteReady(page, '/schedules')
  const generateResponse = page.waitForResponse(
    (response) => response.url().includes('/api/v1/scheduler/generate')
      && response.request().method() === 'POST',
    { timeout: OPERATION_TIMEOUT_MS },
  )
  await page.getByRole('button', { name: /(?:Gerar|Atualizar) Hor.rio/i }).click()
  await page.getByRole('button', { name: /Iniciar gera/i }).click()
  const response = await generateResponse
  const responseText = await response.text()
  expect(response.ok(), `scheduler generate failed: ${response.status()} ${responseText}`).toBeTruthy()
  const job = await waitForSchedulerJob(page, JSON.parse(responseText).job.id)
  expect(job.status).toBe('SUCCEEDED')
  await expect(page.getByText(/Proposta pronta para revis/i)).toBeVisible({ timeout: 30_000 })
  const approvalResponsePromise = page.waitForResponse(
    (candidate) => candidate.url().includes('/api/v1/scheduler/drafts/')
      && candidate.url().endsWith('/approve')
      && candidate.request().method() === 'POST',
    { timeout: OPERATION_TIMEOUT_MS },
  )
  await page.getByRole('button', { name: /^Aprovar$/i }).click()
  const approvalResponse = await approvalResponsePromise
  expect(
    approvalResponse.ok(),
    `draft approval failed: ${approvalResponse.status()} ${await approvalResponse.text()}`,
  ).toBeTruthy()
  return job
}

function mondayIso(value) {
  const monday = new Date(value)
  monday.setHours(12, 0, 0, 0)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return monday.toISOString().slice(0, 10)
}

test.describe('Scheduler generation', () => {
  test.use({ storageState: '.auth/admin.json' })

  test('admin publishes and manages occurrence decisions', async ({ page }) => {
    test.setTimeout(180_000)

    attachRuntimeGuards(page)
    allowApiFailure(page, { status: 409, url: '/api/v1/scheduler/generate' })
    allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
    await loginAsAdminReal(page)
    await goTo(page, '/dashboard')
    const { classId } = await seedMinimalSchedulerInputs(page)

    await goTo(page, '/schedules')
    await expectRouteReady(page, '/schedules')
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)

    const generateResponse = page.waitForResponse(
      (response) => response.url().includes('/api/v1/scheduler/generate')
        && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: /Gerar Hor.rio/i }).click()
    await page.getByRole('button', { name: /Iniciar gera/i }).click()
    const response = await generateResponse
    const responseText = await response.text()
    expect(response.ok(), `scheduler generate failed: ${response.status()} ${responseText}`).toBeTruthy()
    const { job: { id: jobId } } = JSON.parse(responseText)

    const job = await waitForSchedulerJob(page, jobId)
    expect(job.status).toBe('SUCCEEDED')

    await expect(page.getByText(/Proposta pronta para revis/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Proposta pendente').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Resultado completo').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)

    const approvalResponsePromise = page.waitForResponse(
      (candidate) => candidate.url().includes('/api/v1/scheduler/drafts/')
        && candidate.url().endsWith('/approve')
        && candidate.request().method() === 'POST',
    )
    await page.getByRole('button', { name: /^Aprovar$/i }).click()
    const approvalResponse = await approvalResponsePromise
    expect(
      approvalResponse.ok(),
      `draft approval failed: ${approvalResponse.status()} ${await approvalResponse.text()}`,
    ).toBeTruthy()

    const weekStart = FIXTURE.schoolStartDate
    const publishedSlots = await apiRequest(
      page,
      'GET',
      `/schedule/week?class_id=${classId}&week_start=${weekStart}`,
    )
    const activeSlots = publishedSlots.filter((slot) => slot.scheduler_lesson_id)
    expect(activeSlots.length).toBeGreaterThanOrEqual(2)
    const activeLessonIds = new Set(
      activeSlots.map((slot) => slot.scheduler_lesson_id),
    )

    const futureSlot = activeSlots.find(
      (slot) => new Date(slot.ends_at).getTime() > Date.now(),
    )
    expect(futureSlot, 'a published future lesson is required').toBeTruthy()

    // A future lesson cannot be completed before it ends.
    allowApiFailure(page, { status: 422, url: '/api/v1/schedule/lessons/' })
    let completionRejected = false
    try {
      await apiRequest(
        page,
        'PUT',
        `/schedule/lessons/${futureSlot.scheduler_lesson_id}/log`,
        { status: 'COMPLETED', summary: 'E2E too early' },
      )
    } catch (error) {
      completionRejected = /422/.test(String(error))
        && /lesson_not_finished/.test(String(error))
    }
    expect(completionRejected).toBe(true)

    // Registering the occurrence creates neither debt nor execution.
    const occurrenceLog = await apiRequest(
      page,
      'PUT',
      `/schedule/lessons/${futureSlot.scheduler_lesson_id}/log`,
      { status: 'OCCURRENCE', summary: 'E2E occurrence registration' },
    )
    expect(occurrenceLog.status).toBe('OCCURRENCE')
    expect(occurrenceLog.debt_minutes).toBe(0)
    const occurrenceLessonId = occurrenceLog.lesson_id
    expect(activeLessonIds.has(occurrenceLessonId)).toBe(true)

    await goTo(page, `/schedules?weekStart=${weekStart}`)
    await expectRouteReady(page, '/schedules')
    await page.getByLabel('Turma').selectOption(String(classId))
    await expect(page.getByRole('gridcell', { name: /Ocorr.ncia/i }).first()).toBeVisible({
      timeout: 20_000,
    })

    const refreshedSlots = await apiRequest(
      page,
      'GET',
      `/schedule/week?class_id=${classId}&week_start=${weekStart}`,
    )
    const occurrenceSlot = refreshedSlots.find(
      (slot) => slot.scheduler_lesson_id === occurrenceLessonId,
    )
    expect(occurrenceSlot).toMatchObject({ lesson_log_status: 'OCCURRENCE' })

    // A pending occurrence creates no debt. The GAP decision creates it once.
    const debtsBefore = await apiRequest(page, 'GET', `/occurrences/debts?class_id=${classId}`)
    const pending = await apiRequest(
      page,
      'GET',
      `/occurrences/?class_id=${classId}&status=OPEN_PENDING`,
    )
    const occurrence = pending.items.find(
      (item) => item.class_id === classId && item.date === occurrenceSlot.date,
    ) ?? pending.items[0]
    expect(occurrence).toBeTruthy()
    const decided = await apiRequest(
      page,
      'PATCH',
      `/occurrences/${occurrence.id}`,
      { status: 'GAP', version: occurrence.version },
    )
    expect(decided.operational_state).toBe('DECIDED_GAP')
    const debtsAfter = await apiRequest(page, 'GET', `/occurrences/debts?class_id=${classId}`)
    expect(debtsAfter.total_hours_owed).toBeGreaterThan(debtsBefore.total_hours_owed)
  })
})

test('fresh founder completes Complete Generation and custom-rule Adaptive Repair', async ({
  page,
  context,
}) => {
  test.setTimeout(COMPOSED_FLOW_TIMEOUT_MS)
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for the beta remediation journey.')
  const client = createClerkClient({ secretKey })
  const runKey = createE2eRunKey()
  const email = `cronos-beta-${runKey}+clerk_test@example.com`
  const schoolName = `Cronos Beta ${runKey}`
  let userId
  let organizationId
  let primaryError = null
  const cleanupErrors = []

  try {
    await test.step('criação Clerk', async () => {
      const user = await withTimeout(
        () => client.users.createUser({
          emailAddress: [email],
          firstName: 'Cronos',
          lastName: 'Beta',
          skipPasswordRequirement: true,
          legalAcceptedAt: new Date(),
          unsafeMetadata: CLERK_LEGAL_UNSAFE_METADATA,
          createOrganizationEnabled: true,
        }),
        'Clerk user creation',
      )
      userId = user.id
      attachRuntimeGuards(page)
      allowApiFailure(page, { status: 404, url: '/api/v1/scheduler/drafts/current' })
      organizationId = await signInUserWithTicket(client, page, userId, '/foundation', {
        organizationName: schoolName,
      })
      expect(organizationId).toMatch(/^org_/)
    }, { timeout: 120_000 })

    await test.step('Foundation', async () => {
      await page.waitForURL('**/foundation', { timeout: OPERATION_TIMEOUT_MS })
      await page.waitForFunction(
        (expectedOrganizationId) => window.Clerk?.organization?.id === expectedOrganizationId,
        organizationId,
        { timeout: OPERATION_TIMEOUT_MS },
      )

      await page.locator('#school_start_date').fill(FRESH_FOUNDER_DATES.schoolStartDate)
      await page.locator('#school_hard_end_date').fill(FRESH_FOUNDER_DATES.schoolHardEndDate)
      for (let step = 1; step < 8; step += 1) {
        await page.getByRole('button', { name: /seguinte/i }).click()
      }
      const automaticHolidays = page.getByRole('checkbox', { name: /feriados automáticos/i })
      await expect(automaticHolidays).not.toBeChecked()
      const draftSaveResponse = page.waitForResponse((response) => (
        response.url().includes('/api/v1/foundation/draft') &&
        response.request().method() === 'PUT' &&
        response.status() === 200
      ))
      await automaticHolidays.check()
      await draftSaveResponse
      await page.getByRole('button', { name: /seguinte/i }).click()
      await page.getByRole('button', { name: /ignorar por agora/i }).click()
      await page.locator('#foundation-confirmation').check()
      await page.getByRole('button', { name: /^ativar escola$/i }).click()
      await expectRouteReady(page, '/dashboard')
      await expect(page.locator('aside a[href="/dashboard"]').first()).toBeVisible()
      await apiRequest(page, 'GET', '/members/me')
    }, { timeout: 120_000 })

    const { classId, teacherId } = await test.step('preparação dos dados', () => (
      seedMinimalSchedulerInputs(page, email, FRESH_FOUNDER_DATES)
    ), { timeout: 120_000 })

    await test.step('geração completa', async () => {
      const job = await generateAndApproveThroughUi(page)
      expect(job.strategy).toBe('COMPLETE_GENERATION')
    }, { timeout: 180_000 })

    const forbidden = await test.step('seleção da aula a bloquear', () => (
      firstPublishedFutureSlot(page, classId)
    ), { timeout: OPERATION_TIMEOUT_MS })

    const repairJob = await test.step('reparação adaptativa', async () => {
      await apiRequest(page, 'POST', '/schedule/constraints/', {
        rule_type: 'teacher_unavailable',
        rule_payload: {
          teacher_id: teacherId,
          date: forbidden.date,
          timeslot_id: forbidden.timeslot.id,
        },
      })
      await expect.poll(
        async () => (await apiRequest(page, 'GET', '/scheduler/status')).eligibility.reasons.includes('PLANNING_CHANGE'),
        { timeout: OPERATION_TIMEOUT_MS },
      ).toBe(true)
      const job = await generateAndApproveThroughUi(page)
      expect(job.strategy).toBe('ADAPTIVE_RECOVERY')
      return job
    }, { timeout: 180_000 })

    await test.step('validação da reparação', async () => {
      const repairedWeek = await apiRequest(
        page,
        'GET',
        `/schedule/week?class_id=${classId}&week_start=${mondayIso(new Date(`${forbidden.date}T12:00:00`))}`,
      )
      expect(repairedWeek.some((slot) => (
        slot.scheduler_lesson_id
        && slot.date === forbidden.date
        && slot.timeslot.id === forbidden.timeslot.id
        && slot.teacher.id === teacherId
      ))).toBe(false)
      expect(repairJob.strategy).toBe('ADAPTIVE_RECOVERY')
    }, { timeout: 60_000 })

    await test.step('sessão e troca de organização', async () => {
      await page.reload()
      await expectRouteReady(page, '/schedules')
      const secondPage = await context.newPage()
      try {
        attachRuntimeGuards(secondPage)
        await goTo(secondPage, '/schedules')
        await expectRouteReady(secondPage, '/schedules')
      } finally {
        await withTimeout(() => secondPage.close(), 'secondary page close', OPERATION_TIMEOUT_MS)
      }

      await withTimeout(() => clerk.signOut({ page }), 'Clerk sign out')
      await signInUserWithTicket(client, page, userId, '/dashboard')
      await goTo(page, '/schedules')
      await expectRouteReady(page, '/schedules')

      await page.evaluate(async () => window.Clerk.setActive({ organization: null }))
      await page.evaluate(async (organizationId) => window.Clerk.setActive({ organization: organizationId }), organizationId)
      await page.waitForFunction(
        (expectedOrganizationId) => window.Clerk?.organization?.id === expectedOrganizationId,
        organizationId,
        { timeout: OPERATION_TIMEOUT_MS },
      )
      await goTo(page, '/dashboard')
      await expectRouteReady(page, '/dashboard')
    }, { timeout: 120_000 })
  } catch (error) {
    primaryError = error
  } finally {
    if (organizationId) {
      try {
        await withTimeout(
          () => client.organizations.deleteOrganization(organizationId),
          `Clerk organization cleanup ${organizationId}`,
        )
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
    try {
      await cleanupOrganizationByName(client, schoolName)
    } catch (error) {
      cleanupErrors.push(error)
    }
    if (userId) {
      try {
        await withTimeout(() => client.users.deleteUser(userId), `Clerk user cleanup ${userId}`)
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
  }
  if (primaryError) {
    if (cleanupErrors.length) {
      console.error('Cleanup failed after the primary E2E error:', cleanupErrors)
    }
    throw primaryError
  }
  if (cleanupErrors.length) {
    const cleanupError = new Error('E2E cleanup failed')
    cleanupError.errors = cleanupErrors
    throw cleanupError
  }
})
