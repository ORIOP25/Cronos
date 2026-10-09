import { execFile } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'
import { expect } from '@playwright/test'
import { recordCheckpoint } from './acceptance-proof.js'
import { readSchoolResource } from './ui-school.js'
import { canonicalProposalLessons, canonicalSchoolCalendar, schoolDateRange } from './expected-results.js'

export async function readGenerationCalendar(page, original, imported, year) {
  const [settings, gridSettings, events, constraints] = await Promise.all([
    'school/settings/', 'school/grid-settings/', 'school/calendar-events/', 'schedule/constraints/',
  ].map(path => readSchoolResource(page, path)))
  expect(constraints, 'The campaign has not created any manual constraint').toEqual([])
  const dates = schoolDateRange(year.start_date, year.hard_end_date), days = []
  for (let offset = 0; offset < dates.length; offset += 31) {
    const chunk = dates.slice(offset, offset + 31)
    const result = await readSchoolResource(page, `timeslots/range?from_date=${chunk[0]}&to_date=${chunk.at(-1)}`)
    expect(result.days.map(day => day.date)).toEqual(chunk)
    days.push(...result.days)
  }
  const versions = new Map()
  for (const day of days) if (!versions.has(day.version_id)) versions.set(day.version_id, day.date)
  const availability = [], teacherIds = Object.values(imported.identities.teachers)
  for (const [version_id, date] of versions) {
    const timeslots = await readSchoolResource(page, `timeslots/?on_date=${date}`)
    const teachers = []
    for (let offset = 0; offset < teacherIds.length; offset += 6) {
      teachers.push(...await Promise.all(teacherIds.slice(offset, offset + 6).map(async teacher_id => ({
        teacher_id, entries: await readSchoolResource(page, `teachers/${teacher_id}/availability?on_date=${date}`),
      }))))
    }
    availability.push({ version_id, timeslots, teachers })
  }
  const observed = { organization_id: imported.snapshot.organization_id, year, settings, gridSettings, events, constraints, days, availability }
  return { observed, school: canonicalSchoolCalendar(original, imported.identities, observed) }
}

export async function verifyFirstProposalAndApprove(page, testInfo, generated, original, imported) {
  const { observed, school } = await readGenerationCalendar(page, original, imported, generated.status.school_year)
  // A first, unpublished generation must cover all original demand without executed credit.
  expect(generated.status.active_version_id).toBeNull()
  expect(generated.executed).toEqual([])
  const snapshot = { school, executed: [], lessons: generated.lessons }
  const report = await validateMaterializedSchedule(testInfo, snapshot, 'independent-materialized-schedule')
  expect(report).toMatchObject({ valid: true, executed_minutes: 0, lessons: generated.lessons.length })
  const requiredMinutes = original.demand.reduce((sum, row) => sum + row.minutes, 0)
  expect(report.required_minutes).toBe(requiredMinutes)
  expect(report.planned_minutes).toBe(requiredMinutes)
  await testInfo.attach('observed-calendar-and-availability', { body: Buffer.from(JSON.stringify(observed)), contentType: 'application/json' })
  const approved = await approveVerifiedProposal(page, generated)
  await recordCheckpoint(testInfo, [
    'E2E-08/complete-coverage', 'E2E-08/hard-constraints', 'E2E-09/approve-proposal',
  ], { requires: 'school', observation: { proposal_id: generated.proposal.proposal_id, planned_minutes: report.planned_minutes } })
  return { ...approved, report }
}

export async function validateMaterializedSchedule(testInfo, snapshot, label) {
  const snapshotPath = testInfo.outputPath(`${label}.json`)
  await writeFile(snapshotPath, JSON.stringify(snapshot), { mode: 0o600, flag: 'wx' })
  await testInfo.attach(label, { path: snapshotPath, contentType: 'application/json' })
  const { stdout } = await promisify(execFile)(process.env.E2E_PYTHON || 'python', [
    fileURLToPath(new URL('../../../scripts/validate-e2e-schedule.py', import.meta.url)), snapshotPath,
  ], { windowsHide: true, encoding: 'utf8', timeout: 60_000, env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } })
  const report = JSON.parse(stdout)
  expect(report.valid).toBe(true)
  await testInfo.attach(`${label}-validation`, { body: Buffer.from(JSON.stringify(report)), contentType: 'application/json' })
  return report
}

export async function approveVerifiedProposal(page, generated) {
  await page.reload()
  const current = await readSchoolResource(page, 'scheduler/status')
  expect(current).toMatchObject({ active_version_id: generated.status.active_version_id, active_job: null,
    pending_proposal: { proposal_id: generated.proposal.proposal_id, is_stale: false, can_approve: true } })
  expect(current.revisions.input).toBe(generated.status.revisions.input)
  expect(current.revisions.planning).toBe(generated.status.revisions.planning)
  const approvePath = `/api/v1/scheduler/drafts/${generated.proposal.proposal_id}/approve`
  const approvedResponse = page.waitForResponse(response => new URL(response.url()).pathname === approvePath && response.request().method() === 'POST')
  await page.getByRole('region', { name: 'Proposta pendente', exact: true }).getByRole('button', { name: 'Aprovar', exact: true }).click()
  const response = await approvedResponse
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON().expected_input_revision).toBe(current.revisions.input)
  expect(await response.json()).toMatchObject({ proposal_id: generated.proposal.proposal_id, status: 'APPROVED', active_version_id: generated.versionId })
  await expect(page.getByText('Proposta aprovada.', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Proposta pendente', exact: true })).toHaveCount(0)
  await page.reload()
  const published = await readSchoolResource(page, 'scheduler/status')
  expect(published).toMatchObject({ publication_state: 'PUBLISHED', active_version_id: generated.versionId, pending_proposal: null })
  return { versionId: generated.versionId, published }
}

export async function rejectUnpublishedProposal(page, testInfo, generated) {
  await page.goto('/schedules')
  const before = await readSchoolResource(page, 'scheduler/status')
  expect(before).toMatchObject({ publication_state: 'UNPUBLISHED', active_version_id: null, active_job: null,
    pending_proposal: { proposal_id: generated.proposal.proposal_id, is_stale: false } })
  const path = `/api/v1/scheduler/drafts/${generated.proposal.proposal_id}/reject`
  const rejected = page.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'POST')
  await page.getByRole('region', { name: 'Proposta pendente', exact: true }).getByRole('button', { name: 'Rejeitar', exact: true }).click()
  const response = await rejected
  expect(response.status()).toBe(200)
  const decision = await response.json()
  expect(decision).toMatchObject({ proposal_id: generated.proposal.proposal_id, status: 'REJECTED' })
  expect(Date.parse(decision.rejected_at)).toBeGreaterThanOrEqual(Date.parse(generated.job.finished_at))
  await expect(page.getByText('Proposta rejeitada.', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Proposta pendente', exact: true })).toHaveCount(0)
  await page.reload()
  const after = await readSchoolResource(page, 'scheduler/status')
  expect(after).toMatchObject({ publication_state: 'UNPUBLISHED', active_version_id: null, active_job: null,
    pending_proposal: null, eligibility: { can_generate: false, reasons: [], blocker: null } })
  expect(after.revisions).toEqual(before.revisions)
  expect(await readSchoolResource(page, 'scheduler/drafts/current')).toBeNull()
  await expect(page.getByRole('button', { name: 'Gerar horário', exact: true })).toHaveCount(0)
  await testInfo.attach('rejected-proposal-without-publication-or-reroll', {
    body: Buffer.from(JSON.stringify({ before, decision, after })), contentType: 'application/json',
  })
  await recordCheckpoint(testInfo, 'E2E-09/reject-proposal', {
    requires: 'school', observation: { proposal_id: generated.proposal.proposal_id, status: decision.status },
  })
  return after
}

export async function generateProposal(page, testInfo, original, imported, { repair = false, checkpoint = true } = {}) {
  await page.goto('/schedules')
  await page.reload()
  const bases = await readSchoolResource(page, 'readiness/bases')
  expect(bases).toMatchObject({ complete: true, percentage: 100, depth: 6 })
  expect(bases.steps.map(step => step.code)).toEqual(['ACTIVE_CLASSES', 'MODULES', 'TEACHERS', 'TEACHER_ASSIGNMENT', 'COMPATIBLE_ROOM', 'TEACHER_AVAILABILITY'])
  for (const step of bases.steps) expect(step.status).toBe('COMPLETE')
  const prevalidation = await readSchoolResource(page, 'readiness/prevalidation')
  expect(['READY', 'READY_WITH_WARNINGS']).toContain(prevalidation.status)
  const status = await readSchoolResource(page, 'scheduler/status')
  expect(status).toMatchObject({ configured: true, active_job: null, pending_proposal: null })
  if (repair) expect(status.active_version_id).toBeGreaterThan(0)
  else expect(status.active_version_id).toBeNull()
  expect(status.eligibility.can_generate).toBe(true)
  const generate = page.getByRole('button', { name: repair ? 'Atualizar horário' : 'Gerar horário', exact: true })
  await expect(generate).toBeEnabled()
  const requests = []
  const observe = request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/scheduler/generate') requests.push(request)
  }
  page.on('request', observe)
  let admitted
  try {
    await generate.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('heading', { name: 'Confirmar geração', exact: true })).toBeVisible()
    await expect(dialog.getByText(/Âmbito: toda a escola\./)).toBeVisible()
    expect(requests, 'Opening the generation review must not dispatch a job').toHaveLength(0)
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/scheduler/generate' && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Iniciar geração', exact: true }).click()
    const response = await responsePromise
    expect(response.status()).toBe(202)
    admitted = (await response.json()).job
    expect(requests).toHaveLength(1)
    expect(Number.isSafeInteger(admitted.id) && admitted.id > 0).toBe(true)
    expect(admitted.strategy).toBe(repair ? 'ADAPTIVE_RECOVERY' : 'COMPLETE_GENERATION')
    expect(response.request().postDataJSON().expected_input_revision).toBe(status.revisions.input)
  } finally { page.off('request', observe) }
  let job
  const terminal = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE', 'INFEASIBLE', 'INCONCLUSIVE']
  await expect.poll(async () => {
    job = await readSchoolResource(page, `scheduler/jobs/${admitted.id}`)
    return terminal.includes(job.status)
  }, { timeout: 300_000, intervals: [1000, 5000] }).toBe(true)
  expect(job.status).toBe('SUCCEEDED')
  expect(Number.isSafeInteger(job.proposal_id) && job.proposal_id > 0).toBe(true)
  expect(Date.parse(job.finished_at)).toBeGreaterThanOrEqual(Date.parse(job.started_at))
  await expect(page.getByText('Proposta pronta para revisão', { exact: true })).toBeVisible()
  const proposal = await readSchoolResource(page, 'scheduler/drafts/current')
  expect(proposal).toMatchObject({ proposal_id: job.proposal_id, is_stale: false, can_approve: true })
  await expect(page.getByRole('region', { name: 'Proposta pendente', exact: true })).toBeVisible()
  const materialized = await readMaterializedProposal(page, proposal.proposal_id, status.school_year, original, imported)
  await testInfo.attach('materialized-proposal-lessons', { body: Buffer.from(JSON.stringify(materialized)), contentType: 'application/json' })
  await testInfo.attach('generation-job-and-proposal', { body: Buffer.from(JSON.stringify({ bases, prevalidation, job, proposal })), contentType: 'application/json' })
  if (checkpoint) {
    await recordCheckpoint(testInfo, ['E2E-08/generation-confirmation', 'E2E-08/terminal-job'], {
      requires: 'school', observation: { job_id: job.id, job_status: job.status, proposal_id: proposal.proposal_id },
    })
  }
  // Full independent coverage and constraints must be checked before any approval.
  return { job, proposal, status, ...materialized }
}

export async function readMaterializedProposal(page, proposalId, year, original, imported) {
  const lessons = []
  let versionId, total, executed
  do {
    const result = await readSchoolResource(page, `scheduler/drafts/${proposalId}/lessons?skip=${lessons.length}&limit=2000`)
    expect(result).toMatchObject({ proposal_id: proposalId,
      organization_id: imported.snapshot.organization_id, school_year_id: year.id })
    expect(Number.isSafeInteger(result.version_id) && result.version_id > 0).toBe(true)
    expect(Number.isSafeInteger(result.total) && result.total > 0).toBe(true)
    versionId ??= result.version_id
    total ??= result.total
    executed ??= result.executed
    expect(Array.isArray(executed)).toBe(true)
    expect(result.executed).toEqual(executed)
    expect(result.version_id).toBe(versionId)
    expect(result.total).toBe(total)
    expect(result.lessons.length).toBe(Math.min(2000, total - lessons.length))
    lessons.push(...result.lessons)
  } while (lessons.length < total)
  const canonical = canonicalProposalLessons(original, imported.identities, lessons, year.timezone)
  return { versionId, lessons: canonical, rawLessons: lessons, executed }
}
