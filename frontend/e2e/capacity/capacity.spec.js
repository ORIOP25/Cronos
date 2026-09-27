import { expect, test } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'
import { E2E_BASE_URL } from '../utils/e2e-config.js'
import {
  attachRuntimeGuards,
  loginAsAdminReal,
  loginAsTeacherReal,
} from '../utils/clerk-helpers.js'

const smoke = process.env.CAPACITY_PROFILE === 'smoke'
const durationSeconds = Number(process.env.CAPACITY_DURATION_SECONDS || (smoke ? 30 : 600))
const virtualClientCount = smoke ? 4 : 50
const teacherClientCount = smoke ? 3 : 40
const adminClientCount = virtualClientCount - teacherClientCount
const readinessUrl = process.env.CAPACITY_HEALTH_URL || new URL('/health/ready', E2E_BASE_URL).toString()
const teacherRoutes = ['/my-schedules', '/my-availability', '/my-progress']
const adminRoutes = ['/dashboard', '/members', '/courses', '/rooms', '/config', '/schedules']

function percentile(values, percentage) {
  if (!values.length) return null
  const sorted = [...values].sort((left, right) => left - right)
  return sorted[Math.min(sorted.length - 1, Math.ceil((percentage / 100) * sorted.length) - 1)]
}

function createMetrics() {
  return {
    requests: new Map(),
    latencies: [],
    browserErrors: [],
    readinessFailures: 0,
    unexpectedStatuses: 0,
    generation: { acknowledgment_ms: null, completion_ms: null, final_status: null },
  }
}

function addRequest(metrics, response, startedAt) {
  const url = new URL(response.url())
  if (!url.pathname.startsWith('/api/')) return
  const method = response.request().method()
  const key = `${method} ${url.pathname}`
  const latency = Date.now() - startedAt
  const current = metrics.requests.get(key) || { count: 0, statuses: {}, latencies: [] }
  current.count += 1
  current.statuses[response.status()] = (current.statuses[response.status()] || 0) + 1
  current.latencies.push(latency)
  metrics.requests.set(key, current)
  metrics.latencies.push({ method, path: url.pathname, latency })
  if ([401, 403, 409, 429].includes(response.status()) || response.status() >= 500) metrics.unexpectedStatuses += 1
}

async function authenticatedState(browser, login) {
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
  const page = await context.newPage()
  await login(page)
  await page.waitForFunction(() => window.Clerk?.session?.getToken && window.Clerk?.organization?.id)
  const organizationId = await page.evaluate(() => window.Clerk.organization.id)
  const storageState = await context.storageState()
  await context.close()
  return { organizationId, storageState }
}

async function prepareClient(page, route) {
  await page.goto(`${E2E_BASE_URL}${route}`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => window.Clerk?.session?.getToken && window.Clerk?.organization?.id)
}

async function schedulerStatus(page) {
  return page.evaluate(async () => {
    const token = await window.Clerk.session.getToken()
    const response = await fetch('/api/v1/scheduler/status', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return { status: response.status, body: await response.json().catch(() => ({})) }
  })
}

function shiftDate(value, days) {
  const date = new Date(`${value}T12:00:00`)
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

async function ensureGenerationReason(page) {
  const status = await schedulerStatus(page)
  if (status.status >= 400) throw new Error(`Scheduler status failed: ${status.status}`)
  const eligibility = status.body?.eligibility
  if (eligibility?.reasons?.length && !eligibility.blocker) {
    return status.body?.revisions?.input ?? 0
  }
  const year = status.body?.school_year
  if (!year) throw new Error('Capacity smoke requires a configured school year.')
  let preferred = shiftDate(year.preferred_end_date || year.hard_end_date, -1)
  if (preferred < year.start_date) preferred = shiftDate(year.start_date, 1)
  const result = await page.evaluate(async (payload) => {
    const token = await window.Clerk.session.getToken()
    const response = await fetch('/api/v1/school/settings/', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return { status: response.status, body: await response.json().catch(() => ({})) }
  }, {
    school_start_date: year.start_date,
    school_hard_end_date: year.hard_end_date,
    preferred_end_date: preferred,
  })
  if (result.status >= 400) throw new Error(`Planning change was rejected: ${result.status}`)
  const refreshed = await schedulerStatus(page)
  if (refreshed.status >= 400) throw new Error(`Scheduler status failed: ${refreshed.status}`)
  return refreshed.body?.revisions?.input ?? 0
}

async function startOneGeneration(page, metrics) {
  const expectedInputRevision = await ensureGenerationReason(page)
  const startedAt = Date.now()
  const result = await page.evaluate(async (expectedInputRevisionValue) => {
    const token = await window.Clerk.session.getToken()
    const response = await fetch('/api/v1/scheduler/generate', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        idempotency_key: crypto.randomUUID(),
        expected_input_revision: expectedInputRevisionValue,
      }),
    })
    return { status: response.status, body: await response.json().catch(() => ({})) }
  }, expectedInputRevision)
  metrics.generation.acknowledgment_ms = Date.now() - startedAt
  const jobId = result.body?.job?.id
  if (result.status >= 400 || !jobId) throw new Error(`Generation was not acknowledged: ${result.status}`)
  return jobId
}

async function pollGeneration(page, request, jobId, metrics, startedAt) {
  const pollStartedAt = Date.now()
  let finalStatus = null
  while (Date.now() - pollStartedAt < 300_000) {
    const token = await page.evaluate(() => window.Clerk.session.getToken())
    const response = await request.get(`${E2E_BASE_URL}/api/v1/scheduler/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (response.status() >= 400) throw new Error(`Generation status failed: ${response.status()}`)
    finalStatus = (await response.json()).status
    if (['SUCCEEDED', 'FAILED', 'STALE', 'CANCELLED', 'INFEASIBLE', 'INCONCLUSIVE'].includes(finalStatus)) break
    await new Promise((resolve) => setTimeout(resolve, 5000))
  }
  metrics.generation.completion_ms = Date.now() - startedAt
  metrics.generation.final_status = finalStatus
  if (finalStatus !== 'SUCCEEDED') throw new Error(`Generation did not succeed: ${finalStatus || 'timeout'}`)
}

async function runClientLoad(pages, request, metrics, startedAt) {
  const deadline = startedAt + durationSeconds * 1000
  let nextReadinessAt = startedAt
  while (Date.now() < deadline) {
    await Promise.all(pages.map(async ({ page, routes }, index) => {
      const route = routes[Math.floor((Date.now() / 1000 + index) % routes.length)]
      await page.goto(`${E2E_BASE_URL}${route}`, { waitUntil: 'domcontentloaded' })
      const pause = smoke ? 1000 + ((index * 7919) % 2001) : 3000 + ((index * 7919) % 12001)
      await page.waitForTimeout(Math.min(pause, Math.max(0, deadline - Date.now())))
    }))
    if (Date.now() >= nextReadinessAt) {
      const health = await request.get(readinessUrl)
      if (!health.ok()) metrics.readinessFailures += 1
      nextReadinessAt = Date.now() + 5000
    }
  }
}

function revisionForReport() {
  const revision = process.env.GITHUB_SHA || process.env.RAILWAY_GIT_COMMIT_SHA || process.env.VITE_APP_REVISION
  if (!revision) throw new Error('A commit SHA is required for the capacity report.')
  return revision
}

test('mede clientes autenticados com um único job do scheduler', async ({ browser, request }, testInfo) => {
  test.skip(process.env.CAPACITY_ENABLED !== '1', 'Capacity is an explicit launch gate.')
  test.setTimeout((durationSeconds + 360) * 1000)

  const metrics = createMetrics()
  const adminState = await authenticatedState(browser, async (page) => loginAsAdminReal(page))
  const teacherState = await authenticatedState(browser, async (page) => loginAsTeacherReal(page))
  const contexts = []
  const pages = []
  let startedAt = Date.now()
  let failure = null

  try {
    for (let index = 0; index < virtualClientCount; index += 1) {
      const state = index < teacherClientCount ? teacherState : adminState
      const context = await browser.newContext({ storageState: state.storageState })
      const page = await context.newPage()
      const requestStarts = new Map()
      page.on('request', (requestEvent) => requestStarts.set(requestEvent, Date.now()))
      page.on('response', (response) => {
        const request = response.request()
        const requestStartedAt = requestStarts.get(request) || Date.now()
        requestStarts.delete(request)
        addRequest(metrics, response, requestStartedAt)
      })
      page.on('pageerror', (error) => metrics.browserErrors.push(error.name))
      page.on('console', (message) => { if (message.type() === 'error') metrics.browserErrors.push('console.error') })
      attachRuntimeGuards(page)
      contexts.push(context)
      pages.push({ page, routes: index < teacherClientCount ? teacherRoutes : adminRoutes })
    }

    await Promise.all(pages.map(({ page, routes }) => prepareClient(page, routes[0])))
    startedAt = Date.now()
    const generationPage = pages[teacherClientCount]?.page
    if (!generationPage) throw new Error('Capacity profile has no administrator generation page.')
    const loadPages = pages.filter(({ page }) => page !== generationPage)
    const generationStartedAt = Date.now()
    const jobId = await startOneGeneration(generationPage, metrics)
    await Promise.all([
      runClientLoad(loadPages, request, metrics, startedAt),
      pollGeneration(generationPage, request, jobId, metrics, generationStartedAt),
    ])
  } catch (error) {
    failure = error
  } finally {
    const valuesFor = (predicate) => metrics.latencies.filter(predicate).map((item) => item.latency)
    const reads = valuesFor((item) => item.method === 'GET')
    const writes = valuesFor((item) => item.method !== 'GET')
    const report = {
      revision: revisionForReport(),
      environment: process.env.CAPACITY_ENVIRONMENT || E2E_BASE_URL,
      clients: { total: virtualClientCount, teachers: teacherClientCount, administrators: adminClientCount },
      duration_seconds: Math.round((Date.now() - startedAt) / 1000),
      requests_by_endpoint: Object.fromEntries([...metrics.requests.entries()].map(([key, value]) => [key, {
        count: value.count,
        statuses: value.statuses,
        p50_ms: percentile(value.latencies, 50),
        p95_ms: percentile(value.latencies, 95),
        p99_ms: percentile(value.latencies, 99),
      }])),
      latency_ms: {
        reads: { p50: percentile(reads, 50), p95: percentile(reads, 95), p99: percentile(reads, 99) },
        writes: { p50: percentile(writes, 50), p95: percentile(writes, 95), p99: percentile(writes, 99) },
      },
      unexpected_statuses: metrics.unexpectedStatuses,
      browser_errors: metrics.browserErrors,
      readiness_failures: metrics.readinessFailures,
      scheduler: metrics.generation,
      failure: failure?.message || null,
    }
    const reportPath = process.env.CAPACITY_REPORT_PATH || testInfo.outputPath('capacity.json')
    await mkdir(dirname(reportPath), { recursive: true })
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`)
    await Promise.all(contexts.map((context) => context.close()))
  }

  if (failure) throw failure
  const valuesFor = (predicate) => metrics.latencies.filter(predicate).map((item) => item.latency)
  expect(metrics.unexpectedStatuses).toBe(0)
  expect(metrics.browserErrors).toEqual([])
  expect(metrics.readinessFailures).toBe(0)
  expect(percentile(valuesFor((item) => item.method === 'GET'), 95)).toBeLessThan(1000)
  expect(percentile(valuesFor((item) => item.method !== 'GET'), 95)).toBeLessThan(2000)
  expect(metrics.generation.acknowledgment_ms).toBeLessThan(2000)
  expect(metrics.generation.completion_ms).toBeLessThanOrEqual(300000)
  expect(metrics.generation.final_status).toBe('SUCCEEDED')
})
