import { observeAcceptanceRuntime } from './acceptance-runtime.js'
import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'
import { campaignSchoolLabel, validateCodeSender } from './acceptance-policy.js'

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
    : Boolean(await evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.session && window.Clerk?.user)))
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
  const answer = async route => {
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
  // A navigation or the unroute can settle a request while its fetch is in
  // flight; that request needs no answer. Any other route error still fails.
  const handler = async route => {
    // A navigation (an invitation ticket) must keep the browser's own redirects.
    if (route.request().isNavigationRequest?.()) return route.continue()
    try {
      await answer(route)
    } catch (error) {
      if (!/Route is already handled/.test(error?.message || '')) throw error
    }
  }
  await page.route(CLERK_FRONTEND_API, handler)
  try {
    return await perform()
  } finally {
    await page.unroute(CLERK_FRONTEND_API, handler)
  }
}

// A poll read during a navigation sees a destroyed context; that read simply
// has no value yet. Any other page error still fails the poll.
export async function evaluateAcrossNavigation(page, read) {
  try {
    return await page.evaluate(read)
  } catch (error) {
    if (/Execution context was destroyed/.test(error?.message || '')) return undefined
    throw error
  }
}

// The public auth pages are prerendered; their controls only take input once
// the app and Clerk have loaded (an earlier click or fill can be discarded).
export async function awaitClerkLoaded(page) {
  await expect.poll(() => evaluateAcrossNavigation(page, () => window.Clerk?.loaded === true)).toBe(true)
}

export async function expectIdentity(page, email) {
  await expect.poll(() => evaluateAcrossNavigation(page, () => ({
    email: window.Clerk?.user?.primaryEmailAddress?.emailAddress,
    verified: window.Clerk?.user?.primaryEmailAddress?.verification?.status,
    session: Boolean(window.Clerk?.session),
  }))).toEqual({ email, verified: 'verified', session: true })
}

// Reads the newest delivered sign-in code for a dedicated mailbox recipient.
export function deliveredCodeReader(deliveredMail, mailbox, recipient) {
  const sender = validateCodeSender(process.env.E2E_GMAIL_CODE_SENDER)
  return async (after, exclude = []) => (await deliveredMail(mailbox, { recipient, senders: [sender], subject: /^\d{6} is your verification code$/,
    purpose: 'code', after, before: after + 1_200_000, latest: true, exclude })).code
}

// Ends a live session through the visible control; the device stays trusted.
export async function signOutThroughUi(page) {
  if (!(await evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.user)))) return
  await page.goto('/dashboard')
  await awaitClerkLoaded(page)
  await page.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
  await expect.poll(() => evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)
}

export async function login(page, email, password, readCode, runtime) {
  await page.goto('/login')
  await awaitClerkLoaded(page)
  // A trusted device may still hold an earlier session; end it first, as a person would.
  if (await evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.user))) {
    await signOutThroughUi(page)
    await page.goto('/login')
    await awaitClerkLoaded(page)
  }
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  // Clerk's UI asks for the new-device code twice and Clerk may throttle code
  // sends (429 with Retry-After). Only this sign-in's prepare_second_factor 429 is
  // expected, inside this action; every send's outcome is kept for the decision.
  const isCodeSend = request => {
    const url = new URL(request.url())
    return request.method() === 'POST' && url.origin === 'https://clerk.cronos.pt'
      && /^\/v1\/client\/sign_ins\/[A-Za-z0-9_]+\/prepare_second_factor$/.test(url.pathname)
  }
  const sends = []
  const isCodeAttempt = request => request.method() === 'POST' && new URL(request.url()).origin === 'https://clerk.cronos.pt'
    && /^\/v1\/client\/sign_ins\/[A-Za-z0-9_]+\/attempt_second_factor$/.test(new URL(request.url()).pathname)
  // A code Clerk replaced with the duplicate send is rejected (422) before the other one is tried.
  const allowThrottledSend = request => {
    if (!runtime) return
    if (isCodeSend(request)) runtime.allowRequestFailure(request, 429)
    if (isCodeAttempt(request)) runtime.allowRequestFailure(request, 422)
  }
  const recordSend = response => {
    if (isCodeSend(response.request())) sends.push({ status: response.status(), retryAfter: Number(response.headers()['retry-after']) || 0 })
  }
  const signIn = async () => {
    const requestedAt = Date.now()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    // Clerk's client trust asks a new device for an emailed code before the session.
    const code = page.locator('input[autocomplete="one-time-code"]').first()
    const signedIn = () => evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.session && window.Clerk?.user))
    await expect.poll(async () => (await code.isVisible()) || Boolean(await signedIn()), { timeout: 30_000 }).toBe(true)
    if (await code.isVisible()) {
      if (typeof readCode !== 'function') throw new Error('New-device sign-in requires the delivered code reader')
      // A throttled send gets no email: wait as Clerk asks, then use the visible resend control.
      // A send the page cancelled may still have been delivered, so every code since the
      // first click stays a candidate (see the attempt loop below).
      for (let attempt = 0; ; attempt += 1) {
        // The two concurrent sends may answer in either order: a duplicate's 429
        // can arrive before the send that delivered the email.
        const delivered = await expect.poll(() => sends.some(send => send.status < 300), { timeout: 15_000 })
          .toBe(true).then(() => true, () => false)
        if (delivered) break
        if (sends.length === 0) throw new Error('Clerk answered no new-device code send')
        const wait = Math.max(30, ...sends.map(send => send.retryAfter))
        if (attempt === 2 || wait > 600) throw new Error(`Clerk throttled the new-device code: ${sends.map(send => `${send.status}/${send.retryAfter}s`).join(', ')}`)
        sends.length = 0
        await page.waitForTimeout(wait * 1000)
        await page.getByRole('button', { name: /Reenviar/ }).click()
      }
      // Two sends mean two emails whose arrival order may differ from the send
      // order: enter the newest delivered code and, if Clerk rejects it, the other.
      const tried = []
      for (;;) {
        const next = await readCode(requestedAt, tried)
        tried.push(next)
        await code.pressSequentially(next)
        const accepted = await expect.poll(signedIn, { timeout: 15_000 }).toBe(true).then(() => true, () => false)
        if (accepted) break
        if (tried.length === 3) throw new Error('No delivered new-device code was accepted')
        await code.click()
        for (let digit = 0; digit < 6; digit += 1) await page.keyboard.press('Backspace')
      }
    }
    await expectIdentity(page, email)
  }
  const observe = async () => {
    page.on('request', allowThrottledSend)
    page.on('response', recordSend)
    try { await signIn() } finally { page.off('request', allowThrottledSend); page.off('response', recordSend) }
  }
  if (!runtime) return observe()
  await runtime.action('new-device-sign-in', [], observe)
}

export async function loginPersistentActor(page, school, actor, password, readCode) {
  await login(page, actor.email, password, readCode)
  expect(await page.evaluate(() => window.Clerk.user.id)).toBe(actor.id)
  if (await page.evaluate(() => window.Clerk.organization?.id) !== school.clerk_id) {
    await page.getByRole('group', { name: 'Selecionar escola', exact: true }).getByRole('button', { name: 'Abrir seletor de organizações', exact: true }).click()
    await page.getByText(`Cronos Aceitação ${campaignSchoolLabel(school.creation_run_id)}`, { exact: true }).click()
  }
  await expect.poll(() => evaluateAcrossNavigation(page, () => window.Clerk.organization?.id)).toBe(school.clerk_id)
  const member = await readSchoolResource(page, 'members/me')
  expect(member.organization_id).toBe(school.local_id)
  return member
}

// A session opens a new page on its own new browser context or, with
// `context`, on an actor's trusted device, which stays open for later sessions.
export async function freshSession(browser, testInfo, label, perform, { context: device } = {}) {
  const context = device ?? await browser.newContext({ baseURL: 'https://cronos.pt' })
  let page, runtime, primaryError
  // The acceptance projects trace every context natively (`trace: 'on'`).
  try {
    page = await context.newPage()
    runtime = observeAcceptanceRuntime(page)
    await perform(page, runtime)
    await page.waitForLoadState('load')
  } catch (error) { primaryError = error } finally {
    try {
      if (page) await testInfo.attach(`${label}-browser-evidence`, {
        body: await page.screenshot({ fullPage: true, mask: [page.locator('input, textarea')] }), contentType: 'image/png',
      })
    } catch (error) { primaryError ??= error }
    try { await (device ? page?.close() : context.close()) } catch (error) { primaryError ??= error }
    runtime?.dispose()
  }
  if (primaryError) throw primaryError
  expect(runtime.errors, `${label} runtime`).toEqual([])
}
