import { expect } from '@playwright/test'
import { recordCheckpoint } from './acceptance-proof.js'
import { readSchoolResource } from './ui-school.js'
import { openLessonRecord, openTeacherWeek } from './ui-teacher.js'

export async function exerciseHistoricalWeek(teacherPage, adminPage, testInfo, school, horizon, teacherId) {
  let selected
  for (let weekStart = horizon.min_week_start; weekStart && weekStart <= new Date().toISOString().slice(0, 10);) {
    const rows = await readSchoolResource(teacherPage, `schedule/week?week_start=${weekStart}`)
    if (rows.length && rows.every(row => row.block_source === 'planned' && row.scheduler_lesson_id > 0 && row.teacher?.id === teacherId && !row.occurrence_id
      && row.week_timesheet_status === 'OPEN' && Date.parse(row.ends_at) > Date.parse(school.created_at)
      && Date.parse(row.ends_at) <= Date.now()) && rows.some(row => !row.lesson_log_id)) {
      selected = { weekStart, rows }
      break
    }
    weekStart = new Date(Date.parse(`${weekStart}T00:00:00Z`) + 7 * 86_400_000).toISOString().slice(0, 10)
  }
  if (!selected) throw new Error('Historical dependency unavailable: an ended, open week without occurrences is required')
  const weekPath = `schedule/week?week_start=${selected.weekStart}`
  await openTeacherWeek(teacherPage, horizon, selected.weekStart)
  await expect(teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })).toBeDisabled()
  const writes = []
  const observe = request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      writes.push({ path: new URL(request.url()).pathname, method: request.method(), payload: request.postDataJSON() })
    }
  }
  teacherPage.on('request', observe)
  adminPage.on('request', observe)
  try {
    const registrations = []
    for (const original of [...selected.rows].sort((a, b) => Date.parse(a.ends_at) - Date.parse(b.ends_at))) {
      if (original.lesson_log_status === 'COMPLETED') continue
      expect(original.lesson_log_id).toBeFalsy()
      const current = (await readSchoolResource(teacherPage, weekPath)).find(row => row.scheduler_lesson_id === original.scheduler_lesson_id)
      expect(current.can_complete).toBe(true)
      const dialog = await openLessonRecord(teacherPage, current, 'Planeado')
      const summary = `Aceitação ${process.env.E2E_RUN_ID}: fecho semanal, aula ${current.scheduler_lesson_id}.`
      await dialog.getByLabel('Sumário', { exact: true }).fill(summary)
      const path = `/api/v1/schedule/lessons/${current.scheduler_lesson_id}/log`
      const saved = teacherPage.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'PUT')
      await dialog.getByRole('button', { name: 'Aula Dada', exact: true }).click()
      expect((await saved).status()).toBe(200)
      await expect(teacherPage.getByText('Registo guardado.', { exact: true })).toBeVisible()
      await expect(dialog).toBeHidden()
      registrations.push({ path, method: 'PUT', payload: { status: 'COMPLETED', summary, notes: '' } })
    }
    const completed = await readSchoolResource(teacherPage, weekPath)
    expect(completed).toHaveLength(selected.rows.length)
    for (const row of completed) {
      expect(row.lesson_log_status).toBe('COMPLETED')
      expect(row.lesson_log_id).toBeGreaterThan(0)
      expect(Date.parse(row.lesson_log_logged_at)).toBeGreaterThanOrEqual(Date.parse(row.ends_at))
    }
    const progress = await readSchoolResource(teacherPage, 'teachers/me/progress')
    const creditSnapshot = rows => rows.map(row => ({ id: row.scheduler_lesson_id, starts_at: row.starts_at, ends_at: row.ends_at,
      log_id: row.lesson_log_id, summary: row.lesson_log_summary, notes: row.lesson_log_notes, slices: row.slices })).sort((a, b) => a.id - b.id)
    const credits = creditSnapshot(completed)
    await expect(teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })).toBeEnabled()
    await teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true }).click()
    const submitPath = `/api/v1/timesheets/me/${selected.weekStart}/submit`
    const submittedRequest = teacherPage.waitForResponse(response => new URL(response.url()).pathname === submitPath && response.request().method() === 'POST')
    await teacherPage.getByRole('dialog').getByRole('button', { name: 'Submeter', exact: true }).click()
    const submittedResponse = await submittedRequest
    expect(submittedResponse.status()).toBe(200)
    const submitted = await submittedResponse.json()
    expect(submitted).toMatchObject({ organization_id: school.local_id, teacher_id: teacherId, status: 'SUBMITTED', week_start_date: selected.weekStart })
    expect(submitted.submitted_at).toBeTruthy()
    await expect(teacherPage.getByText('Semana submetida.', { exact: true })).toBeVisible()

    const initialRoster = adminPage.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/timesheets/'
      && new URL(response.url()).searchParams.has('week_start_date'))
    await adminPage.goto('/timesheets')
    await expect(adminPage.getByRole('heading', { name: 'Fecho Semanal', exact: true })).toBeVisible()
    const initialResponse = await initialRoster
    expect(initialResponse.status()).toBe(200)
    let visibleWeek = new URL(initialResponse.url()).searchParams.get('week_start_date')
    for (let step = 0; visibleWeek !== selected.weekStart && step < 104; step++) {
      const backwards = visibleWeek > selected.weekStart
      visibleWeek = new Date(Date.parse(`${visibleWeek}T00:00:00Z`) + (backwards ? -7 : 7) * 86_400_000).toISOString().slice(0, 10)
      const requestedWeek = visibleWeek
      const loaded = adminPage.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/timesheets/'
        && new URL(response.url()).searchParams.get('week_start_date') === requestedWeek)
      await adminPage.getByRole('button', { name: backwards ? 'Semana anterior' : 'Próxima semana', exact: true }).click()
      expect((await loaded).status()).toBe(200)
    }
    expect(visibleWeek).toBe(selected.weekStart)
    const roster = await readSchoolResource(adminPage, `timesheets/?week_start_date=${selected.weekStart}`)
    const record = roster.find(row => row.id === submitted.id && row.teacher_id === teacherId)
    expect(record).toMatchObject({ status: 'SUBMITTED', total_slots: completed.length, registered_slots: completed.length })
    await adminPage.getByRole('button').filter({ hasText: record.teacher_name }).click()
    const statusPath = `/api/v1/timesheets/${submitted.id}/status`
    const approvedRequest = adminPage.waitForResponse(response => new URL(response.url()).pathname === statusPath && response.request().method() === 'PATCH')
    await adminPage.getByRole('button', { name: 'Aprovar', exact: true }).click()
    const approvedResponse = await approvedRequest
    expect(approvedResponse.status()).toBe(200)
    expect(approvedResponse.request().postDataJSON()).toEqual({ status: 'APPROVED' })
    const approved = await approvedResponse.json()
    expect(approved).toMatchObject({ id: submitted.id, status: 'APPROVED', approved_by_membership_id: (await readSchoolResource(adminPage, 'members/me')).member_id })
    expect(approved.approved_at).toBeTruthy()
    await expect(adminPage.getByText('Semana aprovada.', { exact: true })).toBeVisible()

    await openTeacherWeek(teacherPage, horizon, selected.weekStart)
    const closed = await readSchoolResource(teacherPage, weekPath)
    expect(closed.every(row => row.week_timesheet_status === 'APPROVED' && !row.can_complete)).toBe(true)
    expect(creditSnapshot(closed)).toEqual(credits)
    await expect(teacherPage.getByRole('button', { name: 'Submeter Semana', exact: true })).toBeDisabled()
    const locked = await openLessonRecord(teacherPage, closed[0], 'Concluída')
    await expect(locked.getByLabel('Sumário', { exact: true })).toBeDisabled()
    await expect(locked.getByLabel('Notas Opcionais', { exact: true })).toBeDisabled()
    await expect(locked.getByRole('button', { name: 'Guardar alterações', exact: true })).toHaveCount(0)
    await locked.getByRole('button', { name: 'Cancelar', exact: true }).click()
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(progress)

    await adminPage.getByRole('button', { name: 'Reabrir', exact: true }).click()
    const reopenedRequest = adminPage.waitForResponse(response => new URL(response.url()).pathname === statusPath && response.request().method() === 'PATCH')
    const confirmation = adminPage.getByRole('dialog')
    await expect(confirmation).toContainText('Confirmar Reabertura')
    await confirmation.getByRole('button', { name: 'Sim, reabrir', exact: true }).click()
    const reopenedResponse = await reopenedRequest
    expect(reopenedResponse.status()).toBe(200)
    expect(reopenedResponse.request().postDataJSON()).toEqual({ status: 'OPEN' })
    const reopened = await reopenedResponse.json()
    expect(reopened).toMatchObject({ id: submitted.id, status: 'OPEN' })
    await expect(adminPage.getByText('Semana reaberta.', { exact: true })).toBeVisible()
    await openTeacherWeek(teacherPage, horizon, selected.weekStart)
    const open = await readSchoolResource(teacherPage, weekPath)
    expect(open.every(row => row.week_timesheet_status === 'OPEN')).toBe(true)
    expect(creditSnapshot(open)).toEqual(credits)
    const editable = await openLessonRecord(teacherPage, open[0], 'Concluída')
    await expect(editable.getByLabel('Sumário', { exact: true })).toBeEnabled()
    await expect(editable.getByRole('button', { name: 'Guardar alterações', exact: true })).toBeEnabled()
    await editable.getByRole('button', { name: 'Cancelar', exact: true }).click()
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(progress)
    expect(writes.map(({ path, method }) => ({ path, method }))).toEqual([
      ...registrations.map(({ path, method }) => ({ path, method })),
      { path: submitPath, method: 'POST' }, { path: statusPath, method: 'PATCH' }, { path: statusPath, method: 'PATCH' },
    ])
    expect(writes.slice(0, registrations.length)).toEqual(registrations)
    await testInfo.attach('historical-week-submit-approve-lock-reopen', { body: Buffer.from(JSON.stringify({
      organization_id: school.local_id, before: selected, completed, submitted, approved, closed, reopened, open, progress, writes,
    })), contentType: 'application/json' })
    await recordCheckpoint(testInfo, [
      'E2E-12/submit-week', 'E2E-12/approve-week', 'E2E-12/closed-week-blocked', 'E2E-12/reopen-week',
    ], { requires: 'school', observation: { week_start: selected.weekStart, registrations: registrations.length } })
  } finally {
    teacherPage.off('request', observe)
    adminPage.off('request', observe)
  }
}
