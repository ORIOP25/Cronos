import { formatDateLong } from '../../src/utils/formatUtils.js'
import { expect } from '@playwright/test'
import { recordCheckpoint } from './acceptance-proof.js'
import { schoolDateRange, validateInitialTeacherProgress, validatePublishedTeacherWeek } from './expected-results.js'
import { readSchoolResource } from './ui-school.js'

async function verifyVisibleTeacherWeek(page, rows) {
  if (!rows.length) {
    await expect(page.getByText('Não existem blocos planeados para a semana selecionada.', { exact: true })).toBeVisible()
    return
  }
  const grid = page.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
  await expect(grid).toBeVisible()
  const labels = new Map()
  for (const row of rows) {
    const label = `${row.subject.name}, ${row.teacher.name}, ${row.room.name}, Planeado`
    labels.set(label, (labels.get(label) || 0) + 1)
  }
  await expect(grid.locator('[role="gridcell"]:not([aria-label="Célula vazia"])')).toHaveCount(rows.length)
  for (const [name, count] of labels) await expect(grid.getByRole('gridcell', { name, exact: true })).toHaveCount(count)
}

export async function verifyPublishedTeacherSchedule(page, testInfo, generated, original, imported, converted) {
  await page.goto('/my-schedules')
  await expect(page.getByText('Horário publicado', { exact: true })).toBeVisible()
  const member = await readSchoolResource(page, 'members/me')
  expect(member).toMatchObject({ organization_id: imported.snapshot.organization_id,
    member_id: converted.member.id, account_id: converted.member.account_id,
    teacher_id: converted.member.teacher_id, access_status: 'active', lifecycle_status: 'active',
    capabilities: ['teacher'], default_mode: 'teacher' })
  const horizon = await readSchoolResource(page, 'schedule/me/horizon')
  expect(horizon).toMatchObject({ hard_end_date: generated.status.school_year.hard_end_date,
    active_generation_id: `v1-${generated.versionId}` })
  const first = new Date(`${generated.status.school_year.start_date}T00:00:00Z`)
  first.setUTCDate(first.getUTCDate() - (first.getUTCDay() + 6) % 7)
  const weekStarts = schoolDateRange(first.toISOString().slice(0, 10), horizon.hard_end_date).filter((_, index) => index % 7 === 0)
  const weeks = []
  for (const weekStart of weekStarts) {
    const rows = await readSchoolResource(page, `schedule/week?week_start=${weekStart}`)
    const lessons = validatePublishedTeacherWeek(original, imported.identities, member.teacher_id, weekStart, rows, generated.lessons)
    weeks.push({ weekStart, rows, lessons })
  }
  const firstOccupied = weeks.findIndex(week => week.rows.length > 0)
  expect(firstOccupied).toBeGreaterThanOrEqual(0)
  expect(horizon.week_start_recommended).toBe(weekStarts[0])
  await verifyVisibleTeacherWeek(page, weeks[0].rows)
  for (let index = 1; index <= firstOccupied; index += 1) {
    const requested = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/schedule/week' && new URL(response.url()).searchParams.get('week_start') === weeks[index].weekStart)
    await page.getByRole('button', { name: 'Próxima semana', exact: true }).click()
    expect((await requested).status()).toBe(200)
    await verifyVisibleTeacherWeek(page, weeks[index].rows)
  }
  await testInfo.attach('teacher-published-year', { body: Buffer.from(JSON.stringify({ member, horizon, weeks })), contentType: 'application/json' })
  await recordCheckpoint(testInfo, 'E2E-09/teacher-published-schedule', {
    requires: 'school', observation: { teacher_id: member.teacher_id, weeks: weeks.length },
  })
  return { member, week: weeks[firstOccupied] }
}

export async function verifyInitialProgress(page, testInfo, original, imported, teacherId) {
  await page.goto('/my-progress')
  await expect(page.getByRole('heading', { name: 'Meu Progresso', exact: true })).toBeVisible()
  const progress = await readSchoolResource(page, 'teachers/me/progress')
  validateInitialTeacherProgress(original, imported.identities, teacherId, progress)
  for (const schoolClass of progress) {
    const card = page.locator('.card').filter({ has: page.locator('.card-header').getByText(schoolClass.class_name, { exact: true }) })
    await expect(card).toHaveCount(1)
    await expect(card.getByText(`${schoolClass.course_name} · ${schoolClass.grade_level}º ano`, { exact: true })).toBeVisible()
    await expect(card.getByText('Média: 0%', { exact: true })).toBeVisible()
    for (const subject of schoolClass.subjects) await expect(card.getByText(subject.subject_name, { exact: true })).toBeVisible()
    for (const hours of new Set(schoolClass.subjects.map(subject => subject.total_hours))) {
      await expect(card.getByText(`0h / ${hours}h`, { exact: true })).toHaveCount(schoolClass.subjects.filter(subject => subject.total_hours === hours).length)
    }
  }
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Meu Progresso', exact: true })).toBeVisible()
  expect(await readSchoolResource(page, 'teachers/me/progress')).toEqual(progress)
  for (const schoolClass of progress) await expect(page.getByText(schoolClass.class_name, { exact: true })).toBeVisible()
  await testInfo.attach('teacher-new-session-curriculum-progress', { body: Buffer.from(JSON.stringify(progress)), contentType: 'application/json' })
  await recordCheckpoint(testInfo, 'E2E-09/new-session-progress', {
    requires: 'school', observation: { classes: progress.length, teacher_id: teacherId },
  })
}

export async function verifyFutureExecutionAndIncompleteWeek(page, testInfo, week) {
  for (const row of week.rows) {
    expect(Date.parse(row.ends_at)).toBeGreaterThan(Date.now())
    expect(row).toMatchObject({ can_complete: false, blocked_reason: 'lesson_not_finished', lesson_log_id: null, lesson_log_status: null })
  }
  const writes = []
  const observe = request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push(request)
  }
  page.on('request', observe)
  try {
    const submit = page.getByRole('button', { name: 'Submeter Semana', exact: true })
    await expect(submit).toBeDisabled()
    await expect(submit).toHaveAttribute('title', /aula futura.*não registada/)
    const row = week.rows[0]
    const dialog = await openLessonRecord(page, row, 'Planeado')
    await expect(dialog.getByRole('heading', { name: /^Registo de Aula/ })).toBeVisible()
    const explanation = 'Só pode concluir esta aula depois do seu término. Pode preencher o sumário e criar ocorrência antecipadamente.'
    await expect(dialog.getByText(explanation, { exact: true })).toBeVisible()
    await dialog.getByLabel('Sumário', { exact: true }).fill('Aceitação: aula futura sem execução.')
    await expect(dialog.getByRole('button', { name: 'Aula Dada', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(await readSchoolResource(page, `schedule/week?week_start=${week.weekStart}`)).toEqual(week.rows)
    expect(writes, 'Reviewing an unfinished lesson must not execute it or submit the week').toHaveLength(0)
    await testInfo.attach('future-execution-and-incomplete-week-blocked', { body: Buffer.from(JSON.stringify({ weekStart: week.weekStart, rows: week.rows, explanation, businessWrites: writes.length })), contentType: 'application/json' })
    await recordCheckpoint(testInfo, ['E2E-10/premature-execution-blocked', 'E2E-12/incomplete-week-blocked'], {
      requires: 'school', observation: { week_start: week.weekStart, business_writes: writes.length },
    })
  } finally { page.off('request', observe) }
}

export async function saveTeacherPreference(page, testInfo) {
  await page.goto('/my-availability')
  const cell = page.locator('button[data-timeslot-id]').first()
  await expect(cell).toHaveAttribute('aria-label', /estado guardado: Neutro/)
  const timeslotId = Number(await cell.getAttribute('data-timeslot-id'))
  expect(Number.isSafeInteger(timeslotId) && timeslotId > 0).toBe(true)
  await page.getByRole('toolbar', { name: 'Ferramentas de disponibilidade', exact: true }).getByRole('button', { name: 'Preferencial', exact: true }).click()
  await cell.focus()
  await expect(cell).toBeFocused()
  await cell.press('Space')
  await expect(page.locator('[aria-live="polite"]').filter({ hasText: /^1 bloco alterado$/ })).toBeVisible()
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/teachers/me/availability' && response.request().method() === 'PUT')
  await page.getByRole('button', { name: 'Guardar preferências', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(page.getByText('Preferências guardadas.', { exact: true })).toBeVisible()
  await verifyTeacherPreference(page, timeslotId)
  if (testInfo) {
    await testInfo.attach('teacher-availability-persistence', {
      body: Buffer.from(JSON.stringify({ timeslot_id: timeslotId, persisted: true })), contentType: 'application/json',
    })
    await recordCheckpoint(testInfo, 'E2E-06/availability-persistence', {
      requires: 'school', observation: { timeslot_id: timeslotId, persisted: true },
    })
  }
  return timeslotId
}

export async function verifyTeacherPreference(page, timeslotId) {
  await page.goto('/my-availability')
  await page.reload()
  await expect(page.locator(`button[data-timeslot-id="${timeslotId}"]`)).toHaveAttribute('aria-label', /estado guardado: Preferencial/)
  await expect(page.getByRole('button', { name: 'Guardar preferências', exact: true })).toBeDisabled()
}

export async function verifyAdminAvailability(page, email, timeslotId) {
  await page.goto('/members')
  const row = page.getByRole('row').filter({ has: page.getByText(email, { exact: true }) })
  await row.getByRole('button', { name: 'Editar disponibilidade', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator(`button[data-timeslot-id="${timeslotId}"]`)).toHaveAttribute('aria-label', /estado guardado: Preferencial/)
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click()
  await page.reload()
  await row.getByRole('button', { name: 'Editar disponibilidade', exact: true }).click()
  await expect(dialog.locator(`button[data-timeslot-id="${timeslotId}"]`)).toHaveAttribute('aria-label', /estado guardado: Preferencial/)
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click()
}

export async function addAdminPreference(page, testInfo, converted, preservedTimeslotId, previousStatus) {
  const teacherId = converted.member.teacher_id
  const path = `teachers/${teacherId}/availability`
  const before = await readSchoolResource(page, path)
  await page.goto('/members')
  const row = page.getByRole('row').filter({ has: page.getByText(converted.member.email, { exact: true }) })
  await row.getByRole('button', { name: 'Editar disponibilidade', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const cell = dialog.locator('button[data-timeslot-id]').filter({ hasText: /^Neutro$/ }).first()
  await expect(cell).toBeVisible()
  const timeslotId = Number(await cell.getAttribute('data-timeslot-id'))
  expect(Number.isSafeInteger(timeslotId) && timeslotId > 0 && timeslotId !== preservedTimeslotId).toBe(true)
  expect(before.find(entry => entry.timeslot_id === timeslotId)).toMatchObject({ score: 1 })
  await dialog.getByRole('toolbar', { name: 'Ferramentas de disponibilidade', exact: true }).getByRole('button', { name: 'Preferencial', exact: true }).click()
  await cell.focus()
  await cell.press('Space')
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === 'PUT')
  await dialog.getByRole('button', { name: 'Guardar disponibilidade', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON().find(entry => entry.timeslot_id === timeslotId)).toEqual({ timeslot_id: timeslotId, score: 2 })
  await expect(page.getByText('Disponibilidade guardada. Recomendações atualizadas.', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click()
  await page.reload()
  const after = await readSchoolResource(page, path)
  expect([...after].sort((a, b) => a.timeslot_id - b.timeslot_id)).toEqual(before.map(entry => entry.timeslot_id === timeslotId ? { ...entry, score: 2 } : entry).sort((a, b) => a.timeslot_id - b.timeslot_id))
  expect(after.find(entry => entry.timeslot_id === preservedTimeslotId)).toMatchObject({ score: 2 })
  const status = await readSchoolResource(page, 'scheduler/status')
  expect(status.revisions.planning).toBeGreaterThan(previousStatus.revisions.planning)
  expect(status).toMatchObject({ active_version_id: null, pending_proposal: null,
    eligibility: { can_generate: true, reasons: ['PLANNING_CHANGE'], blocker: null } })
  await row.getByRole('button', { name: 'Editar disponibilidade', exact: true }).click()
  await expect(dialog.locator(`button[data-timeslot-id="${timeslotId}"]`)).toHaveAttribute('aria-label', /estado guardado: Preferencial/)
  await dialog.getByRole('button', { name: 'Fechar', exact: true }).click()
  await testInfo.attach('planning-change-after-rejection', {
    body: Buffer.from(JSON.stringify({ teacher_id: teacherId, timeslot_id: timeslotId, before, after, status })), contentType: 'application/json',
  })
  await recordCheckpoint(testInfo, 'E2E-07/readiness', {
    requires: 'school', observation: { teacher_id: teacherId, can_generate: status.eligibility.can_generate },
  })
}

export async function openLessonRecord(page, row, status) {
  const label = `${row.subject.name}, ${row.teacher.name}, ${row.room.name}, ${status}`
  // The same subject can occur several times. Match the physical interval too.
  const cell = page.getByRole('table', { name: 'Grelha semanal de horários', exact: true })
    .getByRole('gridcell', { name: label, exact: true })
    .filter({ has: page.getByRole('button', { name: `Abrir registo de ${row.subject.name}`, exact: true }) })
  await expect(cell.first()).toBeVisible()
  const candidates = await cell.all()
  const interval = `${row.timeslot.start_time} – ${row.timeslot.end_time}`
  for (const candidate of candidates) {
    await candidate.getByRole('button').click()
    const dialog = page.getByRole('dialog')
    const text = await dialog.innerText()
    if (text.includes(interval) && text.includes(row.class_info.name) && text.includes(formatDateLong(row.date))) return dialog
    await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  throw new Error('Eligible physical lesson is not visible in the native week grid')
}

export async function openTeacherWeek(page, horizon, weekStart) {
  await page.goto('/my-schedules')
  await expect(page.getByText('Horário publicado', { exact: true })).toBeVisible()
  let visibleWeek = horizon.week_start_recommended
  const direction = visibleWeek > weekStart ? 'Semana anterior' : 'Próxima semana'
  for (let step = 0; visibleWeek !== weekStart && step < 104; step++) {
    const offset = direction === 'Semana anterior' ? -7 : 7
    const requestedWeek = new Date(Date.parse(`${visibleWeek}T00:00:00Z`) + offset * 86_400_000).toISOString().slice(0, 10)
    const loaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/schedule/week'
      && new URL(response.url()).searchParams.get('week_start') === requestedWeek)
    await page.getByRole('button', { name: direction, exact: true }).click()
    expect((await loaded).status()).toBe(200)
    visibleWeek = requestedWeek
  }
  expect(visibleWeek).toBe(weekStart)
}
