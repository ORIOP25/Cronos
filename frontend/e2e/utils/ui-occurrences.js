import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'
import { openLessonRecord, openTeacherWeek } from './ui-teacher.js'
import { validateExecutedLessonCredit } from './expected-results.js'

async function createPendingOccurrence(page, slot, weekStart, summary) {
  const dialog = await openLessonRecord(page, slot, 'Planeado')
  await dialog.getByLabel('Sumário', { exact: true }).fill(summary)
  await dialog.getByRole('button', { name: 'Criar Ocorrência', exact: true }).click()
  await expect(dialog.getByText('Criar ocorrência?', { exact: true })).toBeVisible()
  const path = `/api/v1/schedule/lessons/${slot.scheduler_lesson_id}/log`
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'PUT')
  await dialog.getByRole('button', { name: 'Sim, criar ocorrência', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({ status: 'OCCURRENCE', summary, notes: '' })
  await expect(page.getByText('Registo guardado.', { exact: true })).toBeVisible()
  await expect(dialog).toBeHidden()
  const row = (await readSchoolResource(page, `schedule/week?week_start=${weekStart}`)).find(item => item.scheduler_lesson_id === slot.scheduler_lesson_id)
  expect(row).toMatchObject({ lesson_log_status: 'OCCURRENCE', can_complete: false })
  expect(row.occurrence_id).toBeGreaterThan(0)
  return row
}

export async function exerciseEndedGiven(teacherPage, adminPage, testInfo, school, horizon, weekStart) {
  const weekPath = `schedule/week?week_start=${weekStart}`
  const beforeWeek = await readSchoolResource(teacherPage, weekPath)
  const beforeDebt = await readSchoolResource(adminPage, 'occurrences/debts')
  const slot = beforeWeek.find(row => row.block_source === 'planned' && row.scheduler_lesson_id && !row.lesson_log_id && !row.occurrence_id
    && row.week_timesheet_status === 'OPEN' && row.can_complete === true && Date.parse(row.ends_at) > Date.parse(school.created_at)
    && Date.parse(row.ends_at) <= Date.now() && row.slices.length
    && row.slices.every(slice => slice.completed_minutes === slice.offset_minutes && slice.remaining_minutes >= slice.minutes)
    && !beforeDebt.items.some(debt => debt.class_id === row.class_info.id && debt.subject_id === row.subject.id && debt.teacher_id === row.teacher.id && debt.hours_owed > 0))
  if (!slot) throw new Error('Historical dependency unavailable: GIVEN requires another ended lesson at the actual frontier without old debt')
  await openTeacherWeek(teacherPage, horizon, weekStart)
  const beforeProgress = await readSchoolResource(teacherPage, 'teachers/me/progress')
  const writes = []
  const observe = request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push({ method: request.method(), path })
  }
  teacherPage.on('request', observe)
  adminPage.on('request', observe)
  try {
    const pendingRow = await createPendingOccurrence(teacherPage, slot, weekStart, `Aceitação ${process.env.E2E_RUN_ID}: decisão após término real.`)
    expect(pendingRow.slices).toEqual(slot.slices)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(beforeProgress)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    const path = `occurrences/${pendingRow.occurrence_id}`
    const pending = await readSchoolResource(adminPage, path)
    expect(pending).toMatchObject({ operational_state: 'OPEN_PENDING', decided_at: null, hours_given: 0 })
    await adminPage.goto(`/absences?occurrence_id=${pending.id}`)
    let dialog = adminPage.getByRole('dialog')
    await expect(dialog.getByRole('button', { name: 'Dada', exact: true })).toBeEnabled()
    await dialog.getByRole('button', { name: 'Dada', exact: true }).click()
    await expect(dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeDisabled()
    await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
    const decided = adminPage.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === 'PATCH')
    await dialog.getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
    const response = await decided
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON()).toEqual({ status: 'GIVEN', version: pending.version, substitute_teacher_id: null, substitute_subject_id: null })
    await expect(adminPage.getByText('Decisão registada.', { exact: true })).toBeVisible()
    const given = await readSchoolResource(adminPage, path)
    expect(given).toMatchObject({ id: pending.id, operational_state: 'DECIDED_GIVEN', substitute_block_id: null })
    expect(given.version).toBeGreaterThan(pending.version)
    expect(Date.parse(given.decided_at)).toBeGreaterThanOrEqual(Date.parse(slot.ends_at))
    const after = (await readSchoolResource(teacherPage, weekPath)).find(row => row.scheduler_lesson_id === slot.scheduler_lesson_id)
    expect(after).toMatchObject({ occurrence_id: pending.id, occurrence_status: 'GIVEN', lesson_log_id: pendingRow.lesson_log_id })
    const minutes = validateExecutedLessonCredit(slot, after)
    const afterProgress = await readSchoolResource(teacherPage, 'teachers/me/progress')
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    await adminPage.reload()
    expect(await readSchoolResource(adminPage, path)).toEqual(given)
    dialog = adminPage.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Dada', exact: true }).click()
    await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
    const repeated = adminPage.waitForResponse(result => new URL(result.url()).pathname === `/api/v1/${path}` && result.request().method() === 'PATCH')
    await dialog.getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
    const repeatedResponse = await repeated
    expect(repeatedResponse.status()).toBe(200)
    expect(repeatedResponse.request().postDataJSON()).toEqual({ status: 'GIVEN', version: given.version, substitute_teacher_id: null, substitute_subject_id: null })
    await expect(adminPage.getByText('Decisão registada.', { exact: true })).toBeVisible()
    expect(await readSchoolResource(adminPage, path)).toEqual(given)
    expect((await readSchoolResource(teacherPage, weekPath)).find(row => row.scheduler_lesson_id === slot.scheduler_lesson_id).slices).toEqual(after.slices)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(afterProgress)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    expect(writes).toEqual([{ method: 'PUT', path: `/api/v1/schedule/lessons/${slot.scheduler_lesson_id}/log` },
      { method: 'PATCH', path: `/api/v1/${path}` }, { method: 'PATCH', path: `/api/v1/${path}` }])
    await testInfo.attach('ended-given-decision-and-idempotent-credit', { body: Buffer.from(JSON.stringify({ slot, pendingRow, pending, given, after, exact_minutes: minutes, beforeProgress, afterProgress, beforeDebt, writes })), contentType: 'application/json' })
  } finally {
    teacherPage.off('request', observe)
    adminPage.off('request', observe)
  }
}

export async function exerciseEndedSubstitution(teacherPage, adminPage, testInfo, school, horizon, weekStart) {
  const writes = []
  const observe = request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push({ method: request.method(), path })
  }
  teacherPage.on('request', observe)
  adminPage.on('request', observe)
  try {
    const weekPath = `schedule/week?week_start=${weekStart}`
    const beforeWeek = await readSchoolResource(teacherPage, weekPath)
    const beforeDebt = await readSchoolResource(adminPage, 'occurrences/debts')
    const beforeProgress = await readSchoolResource(teacherPage, 'teachers/me/progress')
    const slot = beforeWeek.find(row => row.block_source === 'planned' && row.scheduler_lesson_id && !row.lesson_log_id && !row.occurrence_id
      && row.week_timesheet_status === 'OPEN' && row.can_complete === true && Date.parse(row.ends_at) > Date.parse(school.created_at)
      && Date.parse(row.ends_at) <= Date.now())
    if (!slot) throw new Error('Historical dependency unavailable: an ended original lesson is required for substitution and reversal')
    const classPath = `classes/${slot.class_info.id}`
    const beforeClass = await readSchoolResource(adminPage, classPath)
    await openTeacherWeek(teacherPage, horizon, weekStart)
    const pendingRow = await createPendingOccurrence(teacherPage, slot, weekStart, `Aceitação ${process.env.E2E_RUN_ID}: substituição após término real.`)
    const path = `occurrences/${pendingRow.occurrence_id}`
    const pending = await readSchoolResource(adminPage, path)
    expect(pending).toMatchObject({ operational_state: 'OPEN_PENDING', hours_given: 0 })
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(beforeProgress)
    const candidates = await readSchoolResource(adminPage, `${path}/substitutes/recommendations`)
    let candidate, substituteBefore, creditEvidence
    for (const item of candidates) {
      if (item.teacher_id === slot.teacher.id || item.subject_id === slot.subject.id
        || beforeDebt.items.some(debt => debt.class_id === slot.class_info.id && debt.subject_id === item.subject_id && debt.teacher_id === item.teacher_id && debt.hours_owed > 0)) continue
      const frontier = beforeClass.subjects.find(subject => subject.id === item.subject_id)?.modules.find(module => !module.is_completed)
      if (!frontier) continue
      const rows = await readSchoolResource(adminPage, `${weekPath}&teacher_id=${item.teacher_id}`)
      const receipt = rows.find(row => row.class_info.id === slot.class_info.id && row.subject.id === item.subject_id && row.scheduler_lesson_id
        && row.slices.some(slice => slice.module_id === frontier.id && slice.remaining_minutes >= slot.credit_minutes))
      if (receipt) { candidate = item; substituteBefore = rows; creditEvidence = { row: receipt, module_id: frontier.id }; break }
    }
    if (!candidate) throw new Error('Historical dependency unavailable: no real eligible substitute with exact observable frontier credit and no prior debt')
    expect(candidate.class_id).toBe(slot.class_info.id)
    expect(beforeClass.subjects.some(subject => subject.id === candidate.subject_id)).toBe(true)
    const substituteWeekPath = `${weekPath}&teacher_id=${candidate.teacher_id}`
    expect(substituteBefore.filter(row => row.date === slot.date && row.timeslot.start_time.slice(0, 5) < slot.timeslot.end_time.slice(0, 5)
      && slot.timeslot.start_time.slice(0, 5) < row.timeslot.end_time.slice(0, 5))).toEqual([])
    await adminPage.goto(`/absences?occurrence_id=${pending.id}`)
    let dialog = adminPage.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Substituída', exact: true }).click()
    const select = dialog.getByLabel('Candidato recomendado', { exact: true })
    if (!await select.locator(`option[value="${candidate.teacher_id}:${candidate.subject_id}"]`).count()) {
      await dialog.getByRole('button', { name: 'Ver lista completa', exact: true }).click()
    }
    await select.selectOption(`${candidate.teacher_id}:${candidate.subject_id}`)
    await expect(dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeDisabled()
    await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
    const planned = adminPage.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === 'PATCH')
    await dialog.getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
    const plannedResponse = await planned
    expect(plannedResponse.status()).toBe(200)
    expect(plannedResponse.request().postDataJSON()).toEqual({ status: 'SUBSTITUTED', version: pending.version,
      substitute_teacher_id: candidate.teacher_id, substitute_subject_id: candidate.subject_id })
    await expect(adminPage.getByText('Decisão registada.', { exact: true })).toBeVisible()
    const substituted = await readSchoolResource(adminPage, path)
    expect(substituted).toMatchObject({ operational_state: 'DECIDED_SUBSTITUTED', substitute_execution_status: 'PENDING_LOG', hours_given: 0 })
    const debt = await readSchoolResource(adminPage, 'occurrences/debts')
    expect((debt.total_hours_owed - beforeDebt.total_hours_owed) * 60).toBeCloseTo(slot.credit_minutes, 8)
    expect(debt.total_gaps).toBe(beforeDebt.total_gaps + 1)
    const reservedClass = await readSchoolResource(adminPage, classPath)
    expect(reservedClass.subjects.find(subject => subject.id === candidate.subject_id)).toEqual(beforeClass.subjects.find(subject => subject.id === candidate.subject_id))
    const reservedWeek = await readSchoolResource(adminPage, substituteWeekPath)
    const reserved = reservedWeek.find(row => row.operational_block_id === substituted.substitute_block_id)
    expect(reserved).toMatchObject({ block_source: 'operational', is_substituted_block: true, occurrence_id: pending.id,
      lesson_log_id: null, substitute_execution_status: 'PENDING_LOG', can_complete: true, blocked_reason: null,
      class_info: slot.class_info, room: slot.room, date: slot.date, ends_at: slot.ends_at, credit_minutes: slot.credit_minutes,
      teacher: { id: candidate.teacher_id }, subject: { id: candidate.subject_id } })
    expect(reserved.timeslot.start_time).toBe(slot.timeslot.start_time)
    expect(reserved.timeslot.end_time).toBe(slot.timeslot.end_time)
    const originalReservedProgress = await readSchoolResource(teacherPage, 'teachers/me/progress')
    await adminPage.goto(`/schedules?teacherId=${candidate.teacher_id}&weekStart=${weekStart}`)
    dialog = await openLessonRecord(adminPage, reserved, 'Substituição')
    await dialog.getByLabel('Sumário', { exact: true }).fill(`Aceitação ${process.env.E2E_RUN_ID}: execução do substituto.`)
    await expect(dialog.getByRole('button', { name: 'Criar Ocorrência', exact: true })).toBeDisabled()
    await expect(dialog.getByRole('button', { name: 'Aula Dada', exact: true })).toBeEnabled()
    const logPath = `/api/v1/schedule/operational-blocks/${reserved.operational_block_id}/log`
    const executed = adminPage.waitForResponse(response => new URL(response.url()).pathname === logPath && response.request().method() === 'PUT')
    await dialog.getByRole('button', { name: 'Aula Dada', exact: true }).click()
    const executedResponse = await executed
    expect(executedResponse.status()).toBe(200)
    expect(executedResponse.request().postDataJSON()).toEqual({ status: 'COMPLETED', summary: `Aceitação ${process.env.E2E_RUN_ID}: execução do substituto.`, notes: '' })
    await expect(adminPage.getByText('Registo guardado.', { exact: true })).toBeVisible()
    const completed = await readSchoolResource(adminPage, path)
    expect(completed).toMatchObject({ operational_state: 'DECIDED_SUBSTITUTED', substitute_execution_status: 'COMPLETED',
      executed_teacher_id: candidate.teacher_id, substitute_subject_id: candidate.subject_id })
    // hours_given is projected from net CurricularExecutionCredit entries, without display rounding.
    expect(completed.hours_given * 60).toBeCloseTo(slot.credit_minutes, 8)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(debt)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(originalReservedProgress)
    const completedClass = await readSchoolResource(adminPage, classPath)
    expect(completedClass.subjects.find(subject => subject.id === slot.subject.id)).toEqual(reservedClass.subjects.find(subject => subject.id === slot.subject.id))
    const completedWeek = await readSchoolResource(adminPage, substituteWeekPath)
    const credited = completedWeek.find(row => row.scheduler_lesson_id === creditEvidence.row.scheduler_lesson_id)
    expect(credited.slices).toEqual(creditEvidence.row.slices.map(slice => slice.module_id === creditEvidence.module_id
      ? { ...slice, completed_minutes: slice.completed_minutes + slot.credit_minutes, remaining_minutes: slice.remaining_minutes - slot.credit_minutes }
      : slice))
    const logged = completedWeek.find(row => row.operational_block_id === reserved.operational_block_id)
    expect(logged).toMatchObject({ lesson_log_status: 'COMPLETED', substitute_execution_status: 'COMPLETED',
      teacher: reserved.teacher, subject: reserved.subject, class_info: reserved.class_info, room: reserved.room, ends_at: reserved.ends_at })
    expect(logged.lesson_log_id).toBeGreaterThan(0)
    expect(Date.parse(logged.lesson_log_logged_at)).toBeGreaterThanOrEqual(Date.parse(logged.ends_at))
    await adminPage.goto(`/absences?occurrence_id=${pending.id}`)
    expect(await readSchoolResource(adminPage, path)).toEqual(completed)
    await adminPage.getByRole('dialog').getByRole('button', { name: 'Reverter', exact: true }).click()
    const reversal = adminPage.getByRole('dialog').filter({ has: adminPage.getByRole('heading', { name: 'Confirmar reversão', exact: true }) })
    await expect(reversal.getByText(/O registo do substituto será revertido se a semana estiver aberta/)).toBeVisible()
    const cancelled = adminPage.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}/cancel` && response.request().method() === 'POST')
    await reversal.getByRole('button', { name: 'Reverter', exact: true }).click()
    const cancellation = await cancelled
    expect(cancellation.status()).toBe(200)
    expect(cancellation.request().postDataJSON()).toEqual({ version: completed.version, cancel_completed_substitute_log: true })
    await expect(adminPage.getByText('Ocorrência revertida.', { exact: true })).toBeVisible()
    const revoked = await readSchoolResource(adminPage, path)
    expect(revoked).toMatchObject({ id: pending.id, operational_state: 'REVOKED', hours_given: 0 })
    expect(revoked.revoked_at).not.toBeNull()
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    expect(await readSchoolResource(adminPage, classPath)).toEqual(beforeClass)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(beforeProgress)
    const afterWeek = await readSchoolResource(adminPage, substituteWeekPath)
    expect(afterWeek.find(row => row.scheduler_lesson_id === creditEvidence.row.scheduler_lesson_id).slices).toEqual(creditEvidence.row.slices)
    // A real log can allocate an OPEN timesheet; temporal flags are recalculated on every read.
    const balancesAndIdentity = rows => rows.map(row => ({ ...row, timesheet_id: null, can_complete: null, blocked_reason: null, is_past: null }))
    expect(balancesAndIdentity(afterWeek)).toEqual(balancesAndIdentity(substituteBefore))
    await adminPage.reload()
    expect(await readSchoolResource(adminPage, path)).toEqual(revoked)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(beforeDebt)
    expect(writes).toEqual([{ method: 'PUT', path: `/api/v1/schedule/lessons/${slot.scheduler_lesson_id}/log` },
      { method: 'PATCH', path: `/api/v1/${path}` }, { method: 'PUT', path: logPath }, { method: 'POST', path: `/api/v1/${path}/cancel` }])
    await testInfo.attach('ended-substitute-credit-and-explicit-compensation', {
      body: Buffer.from(JSON.stringify({ slot, pending, candidate, substituted, debt, reserved, completed, logged, revoked,
        beforeClass, reservedClass, completedClass, substituteBefore, afterWeek, creditEvidence, credited, beforeProgress, originalReservedProgress, writes })), contentType: 'application/json',
    })
  } finally {
    teacherPage.off('request', observe)
    adminPage.off('request', observe)
  }
}

async function prepareConcurrentDecision(page, occurrence) {
  const path = `occurrences/${occurrence.id}`
  expect(await readSchoolResource(page, path)).toEqual(occurrence)
  await page.goto(`/absences?occurrence_id=${occurrence.id}`)
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: /^Decisão Operacional/ })).toBeVisible()
  await dialog.getByRole('button', { name: 'Substituída', exact: true }).click()
  const candidates = await readSchoolResource(page, `${path}/substitutes/recommendations`)
  expect(candidates.length, 'Concurrent decision requires a real eligible substitute').toBeGreaterThan(0)
  const candidate = candidates[0]
  await dialog.getByLabel('Candidato recomendado', { exact: true }).selectOption(`${candidate.teacher_id}:${candidate.subject_id}`)
  await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
  await expect(dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeEnabled()
  return candidate
}

async function rejectConcurrentDecision(page, runtime, occurrence, candidate, current, debt) {
  const path = `occurrences/${occurrence.id}`
  const expectedPayload = { status: 'SUBSTITUTED', version: occurrence.version,
    substitute_teacher_id: candidate.teacher_id, substitute_subject_id: candidate.subject_id }
  const attempted = []
  const observe = request => {
    if (request.method() !== 'PATCH' || new URL(request.url()).pathname !== `/api/v1/${path}`) return
    attempted.push(request)
    expect(request.postDataJSON()).toEqual(expectedPayload)
    expect(runtime.allowRequestFailure(request, 409)).toBe(true)
  }
  let publicCode
  page.on('request', observe)
  try {
    await runtime.action('stale-occurrence-decision', [], async () => {
      const rejected = page.waitForResponse(response => attempted.includes(response.request()))
      await page.getByRole('dialog').getByRole('button', { name: 'Confirmar decisão', exact: true }).click()
      const response = await rejected
      expect(response.status()).toBe(409)
      publicCode = (await response.json()).detail.code
      expect(publicCode).toBe('conflict')
      await expect(page.getByRole('dialog').getByText(/Atualize os dados e tente novamente\./)).toBeVisible()
      await expect(page.getByRole('dialog').getByRole('button', { name: 'Confirmar decisão', exact: true })).toBeEnabled()
    })
  } finally { page.off('request', observe) }
  expect(attempted).toHaveLength(1)
  expect(await readSchoolResource(page, path)).toEqual(current)
  expect(await readSchoolResource(page, 'occurrences/debts')).toEqual(debt)
  await page.reload()
  await expect(page.getByRole('dialog').getByRole('heading', { name: /^Decisão Operacional/ })).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/Atualize os dados e tente novamente\./)).toHaveCount(0)
  expect(await readSchoolResource(page, path)).toEqual(current)
  return { status: 409, public_code: publicCode, attempted_payload: expectedPayload, current_version: current.version, writes: attempted.length }
}

async function planFutureSubstitution(page, slot, occurrence, debt, weekStart, original, identities) {
  const path = `occurrences/${occurrence.id}`
  const recommendations = await readSchoolResource(page, `${path}/substitutes/recommendations`)
  expect(recommendations.length, 'A real eligible substitute is required; no synthetic candidate is allowed').toBeGreaterThan(0)
  const candidate = recommendations[0]
  const assignment = original.demand.find(row => identities.classes[`${row.course}/${row.class}`] === slot.class_info.id && identities.subjects[row.subject] === candidate.subject_id && identities.teachers[row.teacher] === candidate.teacher_id)
  expect(assignment, 'The recommended substitute must own this full original curricular assignment').toBeDefined()
  expect(candidate.teacher_id).not.toBe(slot.teacher.id)
  expect(candidate.subject_id).not.toBe(slot.subject.id)
  expect(candidate.class_id).toBe(slot.class_info.id)
  const weekPath = `schedule/week?week_start=${weekStart}&teacher_id=${candidate.teacher_id}`
  const beforeWeek = await readSchoolResource(page, weekPath)
  expect(beforeWeek.filter(row => row.date === slot.date && row.timeslot.start_time.slice(0, 5) < slot.timeslot.end_time.slice(0, 5) && slot.timeslot.start_time.slice(0, 5) < row.timeslot.end_time.slice(0, 5))).toEqual([])
  const classPath = `classes/${slot.class_info.id}`
  const beforeClass = await readSchoolResource(page, classPath)
  for (const subject of beforeClass.subjects) {
    expect(subject.completed_hours).toBe(0)
    for (const module of subject.modules) expect(module.hours_completed).toBe(0)
  }
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Substituída', exact: true }).click()
  const select = dialog.getByLabel('Candidato recomendado', { exact: true })
  await expect(select).toBeEnabled()
  await select.selectOption(`${candidate.teacher_id}:${candidate.subject_id}`)
  const confirm = dialog.getByRole('button', { name: 'Confirmar decisão', exact: true })
  await expect(confirm).toBeDisabled()
  await dialog.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
  const responsePending = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === 'PATCH')
  await confirm.click()
  const response = await responsePending
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({ status: 'SUBSTITUTED', version: occurrence.version, substitute_teacher_id: candidate.teacher_id, substitute_subject_id: candidate.subject_id })
  await expect(page.getByText('Decisão registada.', { exact: true })).toBeVisible()
  await expect(dialog).toBeHidden()
  const substituted = await readSchoolResource(page, path)
  expect(substituted).toMatchObject({ id: occurrence.id, operational_state: 'DECIDED_SUBSTITUTED',
    substitute_teacher_id: candidate.teacher_id, substitute_subject_id: candidate.subject_id,
    substitute_execution_status: 'PENDING_LOG', hours_given: 0 })
  expect(substituted.substitute_block_id).toBeGreaterThan(0)
  const afterWeek = await readSchoolResource(page, weekPath)
  const reserved = afterWeek.filter(row => row.operational_block_id === substituted.substitute_block_id)
  expect(reserved).toHaveLength(1)
  expect(reserved[0]).toMatchObject({ block_source: 'operational', is_substituted_block: true,
    occurrence_id: occurrence.id, substitute_execution_status: 'PENDING_LOG',
    teacher: { id: candidate.teacher_id }, subject: { id: candidate.subject_id },
    class_info: { id: slot.class_info.id }, room: { id: slot.room.id }, date: slot.date,
    credit_minutes: slot.credit_minutes, ends_at: slot.ends_at,
    can_complete: false, blocked_reason: 'lesson_not_finished', lesson_log_id: null })
  expect(reserved[0].timeslot.start_time.slice(0, 5)).toBe(slot.timeslot.start_time.slice(0, 5))
  expect(reserved[0].timeslot.end_time.slice(0, 5)).toBe(slot.timeslot.end_time.slice(0, 5))
  expect(afterWeek.filter(row => row.operational_block_id !== substituted.substitute_block_id)).toEqual(beforeWeek)
  expect(await readSchoolResource(page, classPath)).toEqual(beforeClass)
  expect(await readSchoolResource(page, 'occurrences/debts')).toEqual(debt)
  await page.reload()
  expect(await readSchoolResource(page, path)).toEqual(substituted)
  expect(await readSchoolResource(page, weekPath)).toEqual(afterWeek)
  return { candidate, assignment, beforeWeek, afterWeek, beforeClass, substituted, reserved: reserved[0], weekPath }
}

// All writes below originate in visible controls; session inspection is GET-only.
export async function exercisePendingOccurrenceAndGap(teacherPage, adminPage, testInfo, week, original, identities, concurrent) {
  const slot = week.rows[0]
  const before = await readSchoolResource(teacherPage, 'teachers/me/progress')
  const emptyDebt = await readSchoolResource(adminPage, 'occurrences/debts')
  expect(emptyDebt).toMatchObject({ total_gaps: 0, total_hours_owed: 0, items: [] })
  expect(Date.parse(slot.ends_at)).toBeGreaterThan(Date.now())
  const writes = []
  const observe = request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/v1/') && ['PUT', 'PATCH', 'POST', 'DELETE'].includes(request.method())) writes.push({ method: request.method(), path })
  }
  teacherPage.on('request', observe)
  adminPage.on('request', observe)
  try {
    const lesson = await openLessonRecord(teacherPage, slot, 'Planeado')
    await lesson.getByLabel('Sumário', { exact: true }).fill('Aceitação: ocorrência futura, sem execução.')
    await expect(lesson.getByRole('button', { name: 'Aula Dada', exact: true })).toBeDisabled()
    await lesson.getByRole('button', { name: 'Criar Ocorrência', exact: true }).click()
    await expect(lesson.getByText('Criar ocorrência?', { exact: true })).toBeVisible()
    expect(writes).toEqual([])
    const logPath = `/api/v1/schedule/lessons/${slot.scheduler_lesson_id}/log`
    const created = teacherPage.waitForResponse(response => new URL(response.url()).pathname === logPath && response.request().method() === 'PUT')
    await lesson.getByRole('button', { name: 'Sim, criar ocorrência', exact: true }).click()
    expect((await created).status()).toBe(200)
    await expect(teacherPage.getByText('Registo guardado.', { exact: true })).toBeVisible()
    await expect(lesson).toBeHidden()
    const currentWeek = await readSchoolResource(teacherPage, `schedule/week?week_start=${week.weekStart}`)
    const current = currentWeek.find(row => row.scheduler_lesson_id === slot.scheduler_lesson_id)
    expect(current).toMatchObject({ lesson_log_status: 'OCCURRENCE', can_complete: false })
    expect(current.occurrence_id).toBeGreaterThan(0)
    const path = `occurrences/${current.occurrence_id}`
    const pending = await readSchoolResource(adminPage, path)
    expect(pending).toMatchObject({ operational_state: 'OPEN_PENDING', hours_given: 0, decided_at: null,
      class_id: slot.class_info.id, subject_id: slot.subject.id, planned_teacher_id: slot.teacher.id,
      creation_source: 'scheduler_v1' })
    expect(pending.planned_hours * 60).toBeCloseTo(slot.credit_minutes, 8)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(before)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(emptyDebt)
    const concurrentCandidate = await prepareConcurrentDecision(concurrent.page, pending)

    await adminPage.goto(`/absences?occurrence_id=${pending.id}`)
    const decision = adminPage.getByRole('dialog')
    await expect(decision.getByRole('heading', { name: /^Decisão Operacional/ })).toBeVisible()
    await expect(decision.getByRole('button', { name: 'Dada', exact: true })).toBeDisabled()
    await decision.getByRole('button', { name: 'Furo', exact: true }).click()
    const confirm = decision.getByRole('button', { name: 'Confirmar decisão', exact: true })
    await expect(confirm).toBeDisabled()
    await decision.getByLabel('Confirmo esta decisão operacional para a ocorrência selecionada.', { exact: true }).check()
    expect(writes).toEqual([{ method: 'PUT', path: logPath }])
    const gapResponse = adminPage.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === 'PATCH')
    await confirm.click()
    const gapResult = await gapResponse
    expect(gapResult.status()).toBe(200)
    expect(gapResult.request().postDataJSON()).toEqual({ status: 'GAP', version: pending.version, substitute_teacher_id: null, substitute_subject_id: null })
    await expect(adminPage.getByText('Decisão registada.', { exact: true })).toBeVisible()
    await expect(decision).toBeHidden()
    const gap = await readSchoolResource(adminPage, path)
    expect(gap).toMatchObject({ id: pending.id, operational_state: 'DECIDED_GAP', hours_given: 0 })
    expect(gap.version).toBeGreaterThan(pending.version)
    const debt = await readSchoolResource(adminPage, 'occurrences/debts')
    expect(debt).toMatchObject({ total_gaps: 1, total_gaps_overdue: 0, total_hours_owed_overdue: 0 })
    expect(debt.total_hours_owed * 60).toBeCloseTo(slot.credit_minutes, 8)
    expect(debt.items).toHaveLength(1)
    expect(debt.items[0]).toMatchObject({ class_id: slot.class_info.id, subject_id: slot.subject.id, teacher_id: slot.teacher.id, gap_occurrences: 1 })
    expect(debt.items[0].hours_owed * 60).toBeCloseTo(slot.credit_minutes, 8)
    const expectedProgress = structuredClone(before)
    const subject = expectedProgress.find(row => row.class_id === slot.class_info.id).subjects.find(row => row.subject_id === slot.subject.id)
    const firstModule = original.subjects[slot.subject.name].modules[0]
    const debtModuleId = identities.modules[`${slot.subject.name}/${firstModule.code}`]
    const gapProgress = await readSchoolResource(teacherPage, 'teachers/me/progress')
    const displayedDebt = gapProgress.find(row => row.class_id === slot.class_info.id).subjects.find(row => row.subject_id === slot.subject.id).modules.find(module => module.module_id === debtModuleId).hours_debt
    // The progress UI rounds hours to one decimal; the debt endpoint above proves exact minutes.
    expect(Math.abs(displayedDebt - slot.credit_minutes / 60)).toBeLessThanOrEqual(0.050000001)
    expect(displayedDebt * 10).toBeCloseTo(Math.round(displayedDebt * 10), 8)
    subject.modules.find(module => module.module_id === debtModuleId).hours_debt = displayedDebt
    expect(gapProgress).toEqual(expectedProgress)
    const conflict = await rejectConcurrentDecision(concurrent.page, concurrent.runtime, pending, concurrentCandidate, gap, debt)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(expectedProgress)
    await adminPage.reload()
    expect(await readSchoolResource(adminPage, path)).toEqual(gap)
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(debt)
    const reservation = await planFutureSubstitution(adminPage, slot, gap, debt, week.weekStart, original, identities)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(expectedProgress)

    // Return the disposable school to zero debt through the actual reversal UI.
    const reloadedDecision = adminPage.getByRole('dialog')
    await expect(reloadedDecision.getByRole('button', { name: 'Reverter', exact: true })).toBeEnabled()
    await reloadedDecision.getByRole('button', { name: 'Reverter', exact: true }).click()
    const reversal = adminPage.getByRole('dialog').filter({ has: adminPage.getByRole('heading', { name: 'Confirmar reversão', exact: true }) })
    await expect(reversal.getByText(/O histórico será preservado/)).toBeVisible()
    const cancelled = adminPage.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}/cancel` && response.request().method() === 'POST')
    await reversal.getByRole('button', { name: 'Reverter', exact: true }).click()
    const cancellationResponse = await cancelled
    expect(cancellationResponse.status()).toBe(200)
    expect(cancellationResponse.request().postDataJSON()).toEqual({ version: reservation.substituted.version, cancel_completed_substitute_log: true })
    await expect(adminPage.getByText('Ocorrência revertida.', { exact: true })).toBeVisible()
    const revoked = await readSchoolResource(adminPage, path)
    expect(revoked).toMatchObject({ id: pending.id, operational_state: 'REVOKED', hours_given: 0 })
    expect(revoked.revoked_at).not.toBeNull()
    expect(await readSchoolResource(adminPage, 'occurrences/debts')).toEqual(emptyDebt)
    expect(await readSchoolResource(teacherPage, 'teachers/me/progress')).toEqual(before)
    expect(await readSchoolResource(adminPage, reservation.weekPath)).toEqual(reservation.beforeWeek)
    expect(writes).toEqual([{ method: 'PUT', path: logPath }, { method: 'PATCH', path: `/api/v1/${path}` }, { method: 'PATCH', path: `/api/v1/${path}` }, { method: 'POST', path: `/api/v1/${path}/cancel` }])
    await testInfo.attach('future-occurrence-decisions-reservation-and-real-session-conflict', { body: Buffer.from(JSON.stringify({ slot, before, pending, gap, debt, conflict, reservation, revoked, writes })), contentType: 'application/json' })
    return { slot, revoked }
  } finally {
    teacherPage.off('request', observe)
    adminPage.off('request', observe)
  }
}
