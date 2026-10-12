import { observeAcceptanceRuntime } from './acceptance-runtime.js'
import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'

// Bounded normal transition for the real provider UI. A managed challenge that
// auto-completes inside this window still passes; only a persistent, visible
// provider challenge at expiry becomes a fixed dependency error.
export const AUTH_STAGE_TIMEOUT_MS = 30_000
const AUTH_STAGE_INTERVAL_MS = 250
// The bound stays below the email window and the native guards already in place.
const AUTH_STAGE_MAX_TIMEOUT_MS = 120_000
const AUTH_STAGES = new Set(['code', 'authenticated'])

export class AuthStageConfigError extends Error {
  constructor(field) {
    super(`Invalid authentication stage configuration: ${field}`)
    this.name = 'AuthStageConfigError'
    this.code = 'auth_stage_config_invalid'
    this.field = field
  }
}

export class AuthDependencyUnavailableError extends Error {
  constructor(observation) {
    super(`Authentication dependency unavailable during the ${observation.stage} stage`)
    this.name = 'AuthDependencyUnavailableError'
    this.code = 'auth_dependency_unavailable'
    this.observation = observation
  }
}

export class AuthStageTimeoutError extends Error {
  constructor(stage, timeoutMs) {
    super(`Authentication UI did not appear during the ${stage} stage`)
    this.name = 'AuthStageTimeoutError'
    this.code = 'auth_stage_timeout'
    this.observation = { stage, timeout: 'expired', timeout_ms: timeoutMs, certifies_production: false }
  }
}

// Fixed, secret-free marker for an auxiliary evidence-attachment failure. The
// primary provider classification is preserved and this never replaces it.
class AuthDependencyAttachmentError extends Error {
  constructor() {
    super('Authentication dependency observation attachment failed')
    this.name = 'AuthDependencyAttachmentError'
    this.code = 'auth_dependency_attachment_failed'
  }
}

// Exact or dotted-suffix https provider hosts only. Credentialed, plain-http
// and look-alike hosts never match, so an observation can only carry the enum.
export function providerChallengeHost(rawUrl) {
  let url
  try { url = new URL(rawUrl) } catch { return null }
  if (url.protocol !== 'https:' || url.username || url.password) return null
  const host = url.hostname.toLowerCase()
  if (host === 'challenges.cloudflare.com' || host.endsWith('.challenges.cloudflare.com')) return 'challenges.cloudflare.com'
  if (host === 'protect.clerk.com' || host.endsWith('.protect.clerk.com')) return 'protect.clerk.com'
  return null
}

// Native Playwright poll with a hard deadline. It races the probe against the
// bound, so a stalled evaluate/protocol read rejects at timeoutMs instead of
// hanging, and a late target resolution can never report success.
const defaultPoll = (probe, { timeoutMs, intervalMs }) =>
  expect.poll(probe, { timeout: timeoutMs, intervals: [intervalMs] }).toBe(true)

// Fail closed before readState can touch the page: a bad stage, bound or
// adapter is a configuration error, never a silent timeout or success.
function assertAuthStageConfig({ stage, readState, timeoutMs, intervalMs }) {
  if (!AUTH_STAGES.has(stage)) throw new AuthStageConfigError('stage')
  if (typeof readState !== 'function') throw new AuthStageConfigError('readState')
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > AUTH_STAGE_MAX_TIMEOUT_MS) throw new AuthStageConfigError('timeoutMs')
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) throw new AuthStageConfigError('intervalMs')
}

// Small explicit seam: readState is the page adapter and poll is the bounded
// strategy (native expect.poll by default). The domain decision stays here: a
// completed read with a visible provider challenge at expiry is the only case
// classified as a dependency block. A thrown adapter error is rethrown
// unchanged, and a still-in-flight (hung) probe is never classified as a
// provider challenge from an older completed state.
export async function awaitAuthUi({ stage, readState, timeoutMs = AUTH_STAGE_TIMEOUT_MS, intervalMs = AUTH_STAGE_INTERVAL_MS, poll = defaultPoll }) {
  assertAuthStageConfig({ stage, readState, timeoutMs, intervalMs })
  let lastState = null
  let inFlight = 0
  let adapterError = null
  const probe = async () => {
    inFlight += 1
    try {
      const state = await readState()
      lastState = state
      return state.target === true
    } catch (error) {
      adapterError = error
      throw error
    } finally {
      inFlight -= 1
    }
  }
  try {
    await poll(probe, { timeoutMs, intervalMs })
    return
  } catch {
    if (adapterError) throw adapterError
    if (inFlight === 0 && lastState && lastState.challenge) {
      throw new AuthDependencyUnavailableError({ stage, challenge_host: lastState.challenge, visible: true, timeout: 'expired', timeout_ms: timeoutMs, certifies_production: false })
    }
    throw new AuthStageTimeoutError(stage, timeoutMs)
  }
}

// Read-only page adapter: code-input visibility, an authenticated-session
// boolean, and the visible provider challenge host. No auth or token mutation.
// Thrown read errors propagate unchanged; only a genuinely detached frame may
// be skipped during the passive poll.
async function readAuthState(page, stage) {
  const target = stage === 'code'
    ? await page.locator('input[autocomplete="one-time-code"]').first().isVisible()
    : await page.evaluate(() => Boolean(window.Clerk?.session && window.Clerk?.user))
  let challenge = null
  for (const frame of page.frames()) {
    const host = providerChallengeHost(frame.url())
    if (!host) continue
    let visible = false
    try {
      const element = await frame.frameElement()
      visible = element ? await element.isVisible() : false
    } catch (error) {
      if (frame.isDetached()) continue
      throw error
    }
    if (visible) { challenge = host; break }
  }
  return { target, challenge }
}

// Stage guard for the real campaign. The observation is attached only on a
// classified provider block; a plain timeout or page crash stays unchanged. An
// attachment failure never masks the primary classification.
export async function awaitAuthStage(page, { stage, testInfo, timeoutMs = AUTH_STAGE_TIMEOUT_MS } = {}) {
  try {
    await awaitAuthUi({ stage, readState: () => readAuthState(page, stage), timeoutMs })
  } catch (error) {
    if (!(error instanceof AuthDependencyUnavailableError)) throw error
    if (testInfo) {
      try {
        await testInfo.attach(`${stage}-auth-dependency-observation`, {
          body: Buffer.from(JSON.stringify(error.observation)), contentType: 'application/json',
        })
      } catch {
        error.cause = new AuthDependencyAttachmentError()
      }
    }
    throw error
  }
}

const CLERK_FRONTEND_API = 'https://clerk.cronos.pt/v1/**'

// Owner-authorised (2026-10-12) Clerk Testing Token for the registration
// challenge only, applied the way the vendor helper does: the token query
// parameter plus the client's captcha_bypass flag. No retries, no other change;
// the route is removed when the registration settles, success or failure.
export async function withSignUpTestingToken(page, token, perform) {
  if (!/^[A-Za-z0-9_-]{20,200}$/.test(token || '')) throw new Error('A minted Clerk testing token is required for registration')
  const handler = async route => {
    const url = new URL(route.request().url())
    url.searchParams.set('__clerk_testing_token', token)
    const response = await route.fetch({ url: url.toString(), maxRedirects: 0 })
    let json
    try { json = await response.json() } catch { return route.fulfill({ response }) }
    let lifted = false
    for (const holder of [json?.response, json?.client]) {
      if (holder?.captcha_bypass === false) { holder.captcha_bypass = true; lifted = true }
    }
    return lifted ? route.fulfill({ response, json }) : route.fulfill({ response })
  }
  await page.route(CLERK_FRONTEND_API, handler)
  try {
    return await perform()
  } finally {
    await page.unroute(CLERK_FRONTEND_API, handler)
  }
}

export async function expectIdentity(page, email) {
  await expect.poll(() => page.evaluate(() => ({
    email: window.Clerk?.user?.primaryEmailAddress?.emailAddress,
    verified: window.Clerk?.user?.primaryEmailAddress?.verification?.status,
    session: Boolean(window.Clerk?.session),
  }))).toEqual({ email, verified: 'verified', session: true })
}

export async function login(page, email, password) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expectIdentity(page, email)
}

export async function loginPersistentActor(page, school, actor, password) {
  await login(page, actor.email, password)
  expect(await page.evaluate(() => window.Clerk.user.id)).toBe(actor.id)
  if (await page.evaluate(() => window.Clerk.organization?.id) !== school.clerk_id) {
    await page.getByRole('group', { name: 'Selecionar escola', exact: true }).getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
    await page.getByText(`Cronos Aceitação ${school.creation_run_id}`, { exact: true }).click()
  }
  await expect.poll(() => page.evaluate(() => window.Clerk.organization?.id)).toBe(school.clerk_id)
  const member = await readSchoolResource(page, 'members/me')
  expect(member.organization_id).toBe(school.local_id)
  return member
}

export async function freshSession(browser, testInfo, label, perform) {
  const context = await browser.newContext({ baseURL: 'https://cronos.pt' })
  let page, runtime, primaryError
  const trace = testInfo.outputPath(`${label}.zip`)
  try {
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
    page = await context.newPage()
    runtime = observeAcceptanceRuntime(page)
    await perform(page, runtime)
    await page.waitForLoadState('load')
  } catch (error) { primaryError = error } finally {
    try {
      if (page) await testInfo.attach(`${label}-browser-evidence`, {
        body: await page.screenshot({ fullPage: true, mask: [page.locator('input, textarea')] }), contentType: 'image/png',
      })
      await context.tracing.stop({ path: trace })
      await testInfo.attach(`${label}-trace`, { path: trace, contentType: 'application/zip' })
    } catch (error) { primaryError ??= error }
    try { await context.close() } catch (error) { primaryError ??= error }
    runtime?.dispose()
  }
  if (primaryError) throw primaryError
  expect(runtime.errors, `${label} runtime`).toEqual([])
}
