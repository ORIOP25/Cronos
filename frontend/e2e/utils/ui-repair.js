import { expect } from '@playwright/test'
import { recordCheckpoint } from './acceptance-proof.js'
import { canonicalExecutedModules, validateImportedData } from './expected-results.js'
import { readImportedData, readOriginalExpectations, readSchoolResource } from './ui-school.js'
import { approveVerifiedProposal, generateProposal, readGenerationCalendar, readMaterializedProposal, validateMaterializedSchedule } from './ui-generation.js'
import { openTeacherWeek } from './ui-teacher.js'

export async function exerciseHistoricalRepair(teacherPage, adminPage, testInfo, school, horizon, weekStart) {
  const original = await readOriginalExpectations()
  const snapshot = await readImportedData(adminPage)
  const originalEmail = Object.keys(original.teachers)[0]
  const invited = snapshot.teachers.find(row => row.id === school.preparation.teacher_id)
  expect(invited.email).toBe(`professorcronos100+${school.creation_run_id}@gmail.com`)
  // The native invitation changed only this original email. Verify every other original field and relation.
  const normalized = structuredClone(snapshot)
  normalized.teachers.find(row => row.id === invited.id).email = originalEmail
  const imported = { snapshot, identities: validateImportedData(original, normalized) }
  const beforeStatus = await readSchoolResource(adminPage, 'scheduler/status')
  expect(beforeStatus).toMatchObject({ publication_state: 'PUBLISHED', active_job: null, pending_proposal: null })
  expect(beforeStatus.active_proposal_id).toBeGreaterThan(0)
  expect(horizon.active_generation_id).toBe(`v1-${beforeStatus.active_version_id}`)
  const baseline = await readMaterializedProposal(adminPage, beforeStatus.active_proposal_id, beforeStatus.school_year, original, imported)
  expect(baseline.versionId).toBe(beforeStatus.active_version_id)
  const calendarBefore = await readGenerationCalendar(adminPage, original, imported, beforeStatus.school_year)
  const now = Date.now()
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: beforeStatus.school_year.timezone,
    year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const window = calendarBefore.observed.settings.repair_stability_window_days ?? 0
  expect(Number.isSafeInteger(window) && window >= 0).toBe(true)
  const protectedDates = new Set(calendarBefore.observed.days.filter(day => day.date >= today && day.blocks.length > 0).slice(0, window).map(day => day.date))
  const historicalIds = new Set(baseline.rawLessons.filter(row => ['COMPLETED', 'OCCURRENCE'].includes(row.lesson_log_status)).map(row => row.id))
  expect(historicalIds.size).toBeGreaterThan(0)
  const baselineHistory = baseline.lessons.filter(row => historicalIds.has(row.id))
  const protectedLessons = baseline.lessons.filter((row, index) => !historicalIds.has(row.id)
    && (Date.parse(baseline.rawLessons[index].starts_at) <= now || protectedDates.has(row.date)))
  const target = baseline.lessons.find((row, index) => !historicalIds.has(row.id) && !protectedDates.has(row.date)
    && Date.parse(baseline.rawLessons[index].starts_at) > now && calendarBefore.school.teaching_dates.includes(row.date))
  if (!target) throw new Error('Historical dependency unavailable: no editable future lesson can trigger repair')
  const progress = await readSchoolResource(teacherPage, 'teachers/me/progress')
  const beforeWeek = await readSchoolResource(teacherPage, `schedule/week?week_start=${weekStart}`)
  const loggedWeek = beforeWeek.filter(row => ['COMPLETED', 'OCCURRENCE'].includes(row.lesson_log_status))
  expect(loggedWeek.length).toBeGreaterThan(0)
  const eventName = `Aceitação ${process.env.E2E_RUN_ID}: interrupção futura`
  const writes = []
  const observe = request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      writes.push({ path: new URL(request.url()).pathname, method: request.method(), payload: request.postDataJSON() })
    }
  }
  adminPage.on('request', observe)
  teacherPage.on('request', observe)
  try {
    await adminPage.goto('/config')
    await adminPage.getByRole('tab', { name: 'Calendário e interrupções', exact: true }).click()
    await adminPage.getByLabel('Nome do evento', { exact: true }).fill(eventName)
    const displayDate = target.date.split('-').reverse().join('/')
    await adminPage.getByLabel('Início', { exact: true }).fill(displayDate)
    await adminPage.getByLabel('Fim', { exact: true }).fill(displayDate)
    await adminPage.getByLabel('Tipo', { exact: true }).selectOption('school_break')
    const createdRequest = adminPage.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/school/calendar-events/' && response.request().method() === 'POST')
    await adminPage.getByRole('button', { name: 'Adicionar evento', exact: true }).click()
    const createdResponse = await createdRequest
    expect(createdResponse.status()).toBe(200)
    const event = await createdResponse.json()
    expect(event).toMatchObject({ organization_id: school.local_id, name: eventName, start_date: target.date, end_date: target.date, event_type: 'school_break' })
    await expect(adminPage.getByText('Evento adicionado.', { exact: true })).toBeVisible()
    await adminPage.reload()
    expect((await readSchoolResource(adminPage, 'school/calendar-events/')).find(row => row.id === event.id)).toMatchObject(event)
    const changedStatus = await readSchoolResource(adminPage, 'scheduler/status')
    expect(changedStatus.active_version_id).toBe(beforeStatus.active_version_id)
    expect(changedStatus.revisions.planning).toBeGreaterThan(beforeStatus.revisions.planning)
    expect(changedStatus.eligibility.can_generate).toBe(true)
    const generated = await generateProposal(adminPage, testInfo, original, imported, { repair: true, checkpoint: false })
    expect(generated.versionId).not.toBe(baseline.versionId)
    expect(generated.executed).toEqual(baseline.executed)
    const calendar = await readGenerationCalendar(adminPage, original, imported, generated.status.school_year)
    expect(calendar.school.teaching_dates).not.toContain(target.date)
    const history = generated.lessons.filter((row, index) => ['COMPLETED', 'OCCURRENCE'].includes(generated.rawLessons[index].lesson_log_status))
    const planned = generated.lessons.filter(row => !history.includes(row))
    const validation = await validateMaterializedSchedule(testInfo, {
      school: calendar.school, executed: canonicalExecutedModules(original, imported.identities, generated.executed, generated.rawLessons),
      lessons: planned, history, baseline_history: baselineHistory, protected: protectedLessons,
    }, 'independent-historical-repair')
    expect(validation).toMatchObject({ required_minutes: original.required_minutes, historical_lessons: baselineHistory.length,
      protected_lessons: protectedLessons.length, lessons: generated.lessons.length })
    expect(validation.executed_minutes).toBeGreaterThan(0)
    expect(validation.planned_minutes + validation.executed_minutes).toBe(validation.required_minutes)
    expect(planned.some(row => row.date === target.date)).toBe(false)
    const approved = await approveVerifiedProposal(adminPage, generated)
    expect(approved.published.active_proposal_id).toBe(generated.proposal.proposal_id)
    const published = await readMaterializedProposal(adminPage, generated.proposal.proposal_id, generated.status.school_year, original, imported)
    expect(published.lessons).toEqual(generated.lessons)
    expect(published.executed).toEqual(baseline.executed)
    await openTeacherWeek(teacherPage, await readSchoolResource(teacherPage, 'schedule/me/horizon'), weekStart)
    const afterWeek = await readSchoolResource(teacherPage, `schedule/week?week_start=${weekStart}`)
    for (const old of loggedWeek) {
      const current = afterWeek.find(row => row.lesson_log_id === old.lesson_log_id)
      expect(current).toBeTruthy()
      for (const field of ['class_info', 'subject', 'teacher', 'room', 'date', 'lesson_log_status', 'lesson_log_summary', 'lesson_log_notes', 'lesson_log_logged_at', 'ends_at', 'credit_minutes']) {
        expect(current[field], `Historical ${field} is preserved`).toEqual(old[field])
      }
    }
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(progress)
    expect(writes.map(({ path, method }) => ({ path, method }))).toEqual([
      { path: '/api/v1/school/calendar-events/', method: 'POST' }, { path: '/api/v1/scheduler/generate', method: 'POST' },
      { path: `/api/v1/scheduler/drafts/${generated.proposal.proposal_id}/approve`, method: 'POST' },
    ])
    await testInfo.attach('historical-repair-publication-and-preserved-credit', { body: Buffer.from(JSON.stringify({
      beforeStatus, baseline, observedCalendar: calendar.observed, protected_dates: [...protectedDates], event,
      generated, validation, approved, published, beforeWeek, afterWeek, progress, writes,
    })), contentType: 'application/json' })
    await recordCheckpoint(testInfo, [
      'E2E-13/future-change-repair', 'E2E-13/physical-lineage', 'E2E-13/residual-coverage', 'E2E-13/historical-credit-preserved',
    ], { requires: 'school', observation: { target_date: target.date, historical_lessons: baselineHistory.length } })
  } finally {
    adminPage.off('request', observe)
    teacherPage.off('request', observe)
  }
}
