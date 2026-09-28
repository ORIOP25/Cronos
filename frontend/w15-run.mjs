import { createClerkClient } from '@clerk/backend'
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const PROD = 'https://cronos.pt'
const API = 'https://api.cronos.pt'
const ART = 'frontend/.test-artifacts/w15'

const LEGAL_METADATA = {
  cronos_legal_versions: { terms_version: '2026-01', dpa_version: '2026-01', privacy_version: '2026-01' },
}

const SCHOOL = {
  start: '2026-09-14',
  preferred: '2027-06-11',
  hard: '2027-06-30',
  grid: { start_time: '09:00', end_time: '18:00', slot_duration_minutes: 60, break_duration_minutes: 0, days_of_week: [0, 1, 2, 3, 4] },
  lunch: { lunch_window_start: '12:30', lunch_window_end: '14:30', lunch_min_duration_minutes: 60 },
}

const SCENARIOS = {
  smoke: { classes: 2, courses: 1, subjects: 7, modules: 4, moduleHours: 15, teachers: 4, rooms: 3 },
  base: { classes: 48, courses: 4, subjects: 10, modules: 4, moduleHours: 15, teachers: 48, rooms: 24 },
  few_teachers: { classes: 48, courses: 4, subjects: 10, modules: 4, moduleHours: 15, teachers: 24, rooms: 24 },
  few_rooms: { classes: 48, courses: 4, subjects: 10, modules: 4, moduleHours: 15, teachers: 48, rooms: 12 },
  more_hours: { classes: 48, courses: 4, subjects: 10, modules: 4, moduleHours: 25, teachers: 64, rooms: 28 },
  more_modules: { classes: 48, courses: 4, subjects: 10, modules: 6, moduleHours: 15, teachers: 64, rooms: 28 },
  d12: { classes: 12, courses: 2, subjects: 10, modules: 4, moduleHours: 15, teachers: 16, rooms: 10 },
  d12_same: { classes: 12, courses: 1, subjects: 10, modules: 4, moduleHours: 15, teachers: 12, rooms: 6 },
  d24: { classes: 24, courses: 3, subjects: 10, modules: 4, moduleHours: 15, teachers: 28, rooms: 16 },
  d36: { classes: 36, courses: 3, subjects: 10, modules: 4, moduleHours: 15, teachers: 40, rooms: 20 },
  d48_1mod: { classes: 48, courses: 4, subjects: 10, modules: 1, moduleHours: 15, teachers: 48, rooms: 24 },
  d48_2mod: { classes: 48, courses: 4, subjects: 10, modules: 2, moduleHours: 15, teachers: 48, rooms: 24 },
}

function csv(rows) {
  return rows.map((row) => row.map((value) => {
    const text = String(value)
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
  }).join(',')).join('\r\n') + '\r\n'
}

function base64(value) {
  return Buffer.from(value, 'utf8').toString('base64')
}

function buildSchool(scenario, runTag) {
  const subjectCount = scenario.subjects
  const subjects = Array.from({ length: subjectCount }, (_, i) => `Disciplina ${String(i + 1).padStart(2, '0')}`)

  const rooms = [['Nome da sala', 'Tipo de sala', 'Capacidade']]
  for (let i = 0; i < scenario.rooms; i += 1) rooms.push([`Sala ${String(i + 1).padStart(2, '0')}`, 'Normal', 30])

  const subjectsCsv = [['Nome da disciplina', 'Tipo de sala', 'Nome do módulo', 'Código do módulo', 'Horas do módulo', 'Ordem do módulo']]
  subjects.forEach((name, si) => {
    for (let m = 0; m < scenario.modules; m += 1) {
      subjectsCsv.push([name, 'Normal', `${name} Módulo ${m + 1}`, `MOD-${si + 1}-${m + 1}`, scenario.moduleHours, m + 1])
    }
  })

  const perCourse = Math.ceil(scenario.classes / scenario.courses)
  const coursesCsv = [['Sigla do curso', 'Nome do curso', 'Nome da turma', 'Ano escolar', 'Ano de início', 'Ano de fim', 'Número de alunos']]
  const classes = []
  for (let c = 0; c < scenario.courses && classes.length < scenario.classes; c += 1) {
    const abbr = `C${String(c + 1).padStart(2, '0')}`
    for (let k = 0; k < perCourse && classes.length < scenario.classes; k += 1) {
      const className = `Turma ${String(classes.length + 1).padStart(2, '0')}`
      coursesCsv.push([abbr, `Curso ${c + 1}`, className, 10, 2026, 2029, 25])
      classes.push({ abbr, className, index: classes.length })
    }
  }

  const teachersCsv = [['Nome do professor', 'Email do professor', 'Nome da disciplina']]
  const teachers = []
  for (let t = 0; t < scenario.teachers; t += 1) {
    const email = `w15-${runTag}-prof${String(t + 1).padStart(3, '0')}@example.com`
    const competencies = new Set()
    for (let c = 0; c < 4; c += 1) competencies.add((t + c) % subjectCount)
    for (const subjectIndex of competencies) teachersCsv.push([`Professor ${String(t + 1).padStart(3, '0')}`, email, subjects[subjectIndex]])
    teachers.push({ email, competencies })
  }

  const assignmentsCsv = [['Sigla do curso', 'Nome da turma', 'Nome da disciplina', 'Email do professor']]
  const cursor = new Map()
  for (const classroom of classes) {
    for (let j = 0; j < 7; j += 1) {
      const subjectIndex = (classroom.index + j) % subjectCount
      const competent = teachers.filter((t) => t.competencies.has(subjectIndex))
      const at = cursor.get(subjectIndex) ?? 0
      const teacher = competent[at % competent.length]
      cursor.set(subjectIndex, at + 1)
      assignmentsCsv.push([classroom.abbr, classroom.className, subjects[subjectIndex], teacher.email])
    }
  }

  const perClassHours = 7 * scenario.modules * scenario.moduleHours
  return {
    rooms: csv(rooms),
    subjects: csv(subjectsCsv),
    courses: csv(coursesCsv),
    teachers: csv(teachersCsv),
    assignments: csv(assignmentsCsv),
    summary: {
      classes: classes.length,
      teachers: teachers.length,
      rooms: scenario.rooms,
      subjects: subjectCount,
      modulesPerSubject: scenario.modules,
      moduleHours: scenario.moduleHours,
      subjectsPerClass: 7,
      hoursPerClass: perClassHours,
      totalDemandHours: classes.length * perClassHours,
      assignments: classes.length * 7,
    },
  }
}

async function api(page, method, path, body) {
  return page.evaluate(async ({ method: m, path: p, body: b }) => {
    const token = await window.Clerk.session.getToken({ organizationId: window.Clerk.organization.id })
    const res = await fetch(`/api/v1${p}`, {
      method: m,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: b === undefined ? undefined : JSON.stringify(b),
    })
    const text = await res.text()
    let json = null
    try { json = text ? JSON.parse(text) : null } catch { json = text }
    return { ok: res.ok, status: res.status, json }
  }, { method, path, body })
}

async function apiAbsolute(page, method, path, body) {
  return page.evaluate(async ({ apiBase, method: m, path: p, body: b }) => {
    const token = await window.Clerk.session.getToken({ organizationId: window.Clerk.organization.id })
    const res = await fetch(`${apiBase}${p}`, {
      method: m,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: b === undefined ? undefined : JSON.stringify(b),
    })
    const text = await res.text()
    let json = null
    try { json = text ? JSON.parse(text) : null } catch { json = text }
    return { ok: res.ok, status: res.status, json }
  }, { apiBase: API, method, path, body })
}

async function waitTerminal(page, jobId, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let job = (await apiAbsolute(page, 'GET', `/api/v1/scheduler/jobs/${jobId}`)).json
  while (!['SUCCEEDED', 'FAILED', 'STALE', 'CANCELLED', 'INFEASIBLE', 'INCONCLUSIVE'].includes(job.status) && Date.now() < deadline) {
    await page.waitForTimeout(5000)
    job = (await apiAbsolute(page, 'GET', `/api/v1/scheduler/jobs/${jobId}`)).json
  }
  return job
}

async function completeFoundation(page) {
  await page.goto(`${PROD}/foundation`, { waitUntil: 'domcontentloaded' })
  const legal = page.getByRole('checkbox', { name: /Confirmo a aceita/i })
  await legal.waitFor({ timeout: 15000 }).catch(() => {})
  if (await legal.isVisible().catch(() => false)) {
    await legal.check()
    await page.getByRole('button', { name: /Confirmar e continuar/i }).click()
  }
  await page.locator('#school_start_date').waitFor({ timeout: 30000 })
  await page.locator('#school_start_date').fill(SCHOOL.start)
  await page.locator('#school_hard_end_date').fill(SCHOOL.hard)
  for (let step = 1; step < 8; step += 1) await page.getByRole('button', { name: /seguinte/i }).click()
  await page.getByRole('checkbox', { name: /feriados automáticos/i }).check()
  await page.getByRole('button', { name: /seguinte/i }).click()
  await page.getByRole('button', { name: /ignorar por agora/i }).click()
  await page.locator('#foundation-confirmation').check()
  await page.getByRole('button', { name: /^ativar escola$/i }).click()
  await page.waitForURL(/dashboard/, { timeout: 90000 })
}

async function runScenario(browser, secretKey, name, scenario) {
  const stamp = Date.now()
  const runTag = `${name}${stamp.toString(36)}`.replace(/[^a-z0-9]/gi, '').toLowerCase()
  const school = buildSchool(scenario, runTag)
  const email = `w15-admin-${runTag}+clerk_test@example.com`
  const schoolName = `W15 ${name} ${stamp}`
  const client = createClerkClient({ secretKey })
  const artifact = { scenario: name, school_name: schoolName, summary: school.summary, started_at: new Date().toISOString() }
  let organizationId
  let userId
  const page = await browser.newPage()
  await page.route('**/api/v1/**', async (route) => {
    const original = new URL(route.request().url())
    if (original.hostname === 'api.cronos.pt') return route.continue()
    const response = await route.fetch({ url: `${API}${original.pathname}${original.search}` })
    await route.fulfill({ response })
  })
  try {
    const user = await client.users.createUser({
      emailAddress: [email], firstName: 'W15', lastName: name,
      skipPasswordRequirement: true, legalAcceptedAt: new Date(), unsafeMetadata: LEGAL_METADATA,
    })
    userId = user.id
    const org = await client.organizations.createOrganization({ name: schoolName, createdBy: userId })
    organizationId = org.id
    const ticket = await client.signInTokens.createSignInToken({ userId, expiresInSeconds: 3600 })
    await page.goto(ticket.url, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => Boolean(window.Clerk?.session), null, { timeout: 90000 })
    await page.evaluate(async (id) => window.Clerk.setActive({ organization: id }), organizationId)
    await page.waitForFunction((id) => window.Clerk?.organization?.id === id, organizationId, { timeout: 60000 })

    console.log(`[${name}] a concluir fundação...`)
    await completeFoundation(page)

    console.log(`[${name}] a configurar datas e grelha...`)
    let res = await api(page, 'POST', '/school/settings/', {
      school_start_date: SCHOOL.start, preferred_end_date: SCHOOL.preferred,
      school_hard_end_date: SCHOOL.hard, repair_stability_window_days: 0,
      automatic_holidays_enabled: true,
    })
    if (!res.ok) throw new Error(`settings: ${res.status} ${JSON.stringify(res.json).slice(0, 300)}`)
    res = await api(page, 'POST', '/school/grid-settings/regenerate', { grid_settings: SCHOOL.lunch, timeslots: SCHOOL.grid })
    if (!res.ok) throw new Error(`grid: ${res.status} ${JSON.stringify(res.json).slice(0, 300)}`)

    console.log(`[${name}] a importar ${school.summary.classes} turmas, ${school.summary.teachers} professores, ${school.summary.assignments} atribuições...`)
    const files = {
      rooms: { filename: 'rooms.csv', content_base64: base64(school.rooms) },
      subjects: { filename: 'subjects.csv', content_base64: base64(school.subjects) },
      courses: { filename: 'courses.csv', content_base64: base64(school.courses) },
      teachers: { filename: 'teachers.csv', content_base64: base64(school.teachers) },
      assignments: { filename: 'assignments.csv', content_base64: base64(school.assignments) },
    }
    const tImport = Date.now()
    const commit = await api(page, 'POST', '/imports/commit', { files })
    artifact.import_seconds = Math.round((Date.now() - tImport) / 100) / 10
    if (!commit.ok) {
      artifact.import_error = commit.json
      throw new Error(`import: ${commit.status} ${JSON.stringify(commit.json).slice(0, 500)}`)
    }
    artifact.created_counts = commit.json?.created_counts ?? null
    artifact.import_warnings = commit.json?.warnings ?? []
    console.log(`[${name}] importado em ${artifact.import_seconds}s: ${JSON.stringify(artifact.created_counts)}`)

    const status = (await api(page, 'GET', '/scheduler/status')).json
    artifact.eligibility = status?.eligibility ?? null
    artifact.school_year = status?.school_year ?? null
    if (!status?.eligibility?.can_generate) {
      throw new Error(`not eligible: ${JSON.stringify(status?.eligibility)}`)
    }
    console.log(`[${name}] a gerar horário (pode demorar até 15 min)...`)
    const tGen = Date.now()
    const admitted = await api(page, 'POST', '/scheduler/generate', {
      idempotency_key: `w15-${name}-${stamp}`, expected_input_revision: status.revisions.input,
    })
    if (!admitted.ok) throw new Error(`generate: ${admitted.status} ${JSON.stringify(admitted.json).slice(0, 400)}`)
    artifact.job_id = admitted.json.job.id
    const job = await waitTerminal(page, admitted.json.job.id, 30 * 60_000)
    artifact.wall_seconds = Math.round((Date.now() - tGen) / 100) / 10
    artifact.job = {
      status: job.status, strategy: job.strategy, result_code: job.result_code,
      stop_reason: job.stop_reason, queued_at: job.queued_at, started_at: job.started_at,
      finished_at: job.finished_at, summary: job.summary ?? null,
    }
    artifact.processing_seconds = (job.started_at && job.finished_at)
      ? Math.round((new Date(job.finished_at) - new Date(job.started_at)) / 100) / 10 : null
    artifact.queue_wait_seconds = (job.queued_at && job.started_at)
      ? Math.round((new Date(job.started_at) - new Date(job.queued_at)) / 100) / 10 : null
    console.log(`[${name}] job ${job.status} / ${job.result_code} / ${job.stop_reason} em ${artifact.processing_seconds}s`)

    if (job.status === 'SUCCEEDED') {
      const proposal = (await api(page, 'GET', '/scheduler/drafts/current')).json
      artifact.quality_summary = proposal?.quality_summary ?? null
      const metrics = proposal?.metrics ?? {}
      artifact.metrics = {
        latest_completion_date: metrics.latest_completion_date ?? null,
        preferred_end_date: metrics.preferred_end_date ?? null,
        hard_end_date: metrics.hard_end_date ?? null,
        margin_days: metrics.margin_days ?? null,
        excess_days: metrics.excess_days ?? null,
        classes_after_preferred: metrics.classes_after_preferred ?? null,
        teacher_gap_minutes: metrics.teacher_gap_minutes ?? null,
        class_gap_minutes: metrics.class_gap_minutes ?? null,
        preference_cost_minutes: metrics.preference_cost_minutes ?? null,
        room_change_cost: metrics.room_change_cost ?? null,
        disruption_cost: metrics.disruption_cost ?? null,
        changed_lessons: metrics.changed_lessons ?? null,
        stop_reason: metrics.stop_reason ?? null,
        certified_stages: metrics.certified_stages ?? null,
        validation: metrics.validation ?? null,
      }
      console.log(`[${name}] excess_days=${artifact.metrics.excess_days} margin_days=${artifact.metrics.margin_days} certified=${artifact.metrics.certified_stages}/${artifact.quality_summary?.total_stages} claims_optimum=${artifact.quality_summary?.claims_optimum}`)
    }
  } catch (error) {
    artifact.error = String(error?.message ?? error)
    console.error(`[${name}] ERRO: ${artifact.error}`)
  } finally {
    await page.close().catch(() => {})
    if (organizationId) await client.organizations.deleteOrganization(organizationId).catch((e) => console.error(`org cleanup: ${e.message}`))
    if (userId) await client.users.deleteUser(userId).catch((e) => console.error(`user cleanup: ${e.message}`))
  }
  artifact.finished_at = new Date().toISOString()
  await mkdir(ART, { recursive: true })
  await writeFile(`${ART}/${name}.json`, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8')
  return artifact
}

async function main() {
  const secretKey = process.env.CLERK_SECRET_KEY
  if (!secretKey) throw new Error('CLERK_SECRET_KEY is required')
  const only = process.argv[2] ? process.argv[2].split(',') : Object.keys(SCENARIOS)
  const browser = await chromium.launch()
  try {
    for (const name of only) {
      const scenario = SCENARIOS[name]
      if (!scenario) { console.error(`cenário desconhecido: ${name}`); continue }
      console.log(`\n===== cenário ${name} =====`)
      const artifact = await runScenario(browser, secretKey, name, scenario)
      console.log(`===== ${name}: ${artifact.error ? 'ERRO' : 'OK'} =====`)
    }
  } finally {
    await browser.close()
  }
}

main().catch((error) => { console.error(error); process.exit(1) })
