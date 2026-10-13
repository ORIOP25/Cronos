import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import {
  AuthDependencyUnavailableError,
  AuthStageConfigError,
  AuthStageTimeoutError,
  awaitAuthStage,
  awaitAuthUi,
  providerChallengeHost,
  withSignUpTestingToken,
  evaluateAcrossNavigation,
} from '../e2e/utils/ui-auth.js'

// Deterministic poll strategy for the pure unit: call the probe at most
// `attempts` times, then reject like a native poll timeout. No abstract engine.
function fakePoll(attempts = 4) {
  return async probe => {
    for (let index = 0; index < attempts; index += 1) if (await probe()) return
    throw new Error('fake poll timeout')
  }
}

// Minimal read-only page fixture. It emulates only the surfaces readAuthState
// uses: locator().first().isVisible(), evaluate() and frames(). No live app.
function fakePage({ target = false, challenge = null, readError = null, frameError = null, detached = false } = {}) {
  return {
    locator: () => ({ first: () => ({ isVisible: async () => { if (readError) throw readError; return target } }) }),
    evaluate: async () => { if (readError) throw readError; return target },
    frames: () => (challenge === null ? [] : [{
      url: () => challenge,
      isDetached: () => detached,
      frameElement: async () => { if (frameError) throw frameError; return { isVisible: async () => true } },
    }]),
  }
}

function deferred() {
  let resolve
  const promise = new Promise(next => { resolve = next })
  return { promise, resolve }
}

test('a managed challenge that auto-completes transitions to the target and passes', async () => {
  const states = [
    { target: false, challenge: 'challenges.cloudflare.com' },
    { target: false, challenge: 'challenges.cloudflare.com' },
    { target: true, challenge: null },
  ]
  let reads = 0
  await awaitAuthUi({
    stage: 'code',
    readState: async () => states[Math.min(reads++, states.length - 1)],
    poll: fakePoll(5),
  })
  assert.equal(reads, 3)
})

test('a persistent visible known challenge fails with the fixed dependency error', async () => {
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => ({ target: false, challenge: 'challenges.cloudflare.com' }),
      timeoutMs: 1000,
      poll: fakePoll(3),
    }),
    error => {
      assert.ok(error instanceof AuthDependencyUnavailableError)
      assert.equal(error.code, 'auth_dependency_unavailable')
      assert.deepEqual(error.observation, {
        stage: 'code', challenge_host: 'challenges.cloudflare.com', visible: true, timeout: 'expired', timeout_ms: 1000, certifies_production: false,
      })
      return true
    },
  )
})

test('the provider protect host also classifies as a dependency block', async () => {
  await assert.rejects(
    awaitAuthUi({
      stage: 'authenticated',
      readState: async () => ({ target: false, challenge: 'protect.clerk.com' }),
      timeoutMs: 1000,
      poll: fakePoll(3),
    }),
    error => error instanceof AuthDependencyUnavailableError && error.observation.challenge_host === 'protect.clerk.com',
  )
})

test('a plain timeout without a visible challenge is not classified as a provider block', async () => {
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => ({ target: false, challenge: null }),
      timeoutMs: 1000,
      poll: fakePoll(3),
    }),
    error => error instanceof AuthStageTimeoutError && !(error instanceof AuthDependencyUnavailableError),
  )
})

test('an unexpected page adapter error is not swallowed', async () => {
  const failure = new Error('page crashed')
  await assert.rejects(
    awaitAuthUi({ stage: 'code', readState: async () => { throw failure }, timeoutMs: 1000 }),
    error => error === failure,
  )
})

test('provider host matching accepts exact and suffix https hosts only', () => {
  assert.equal(providerChallengeHost('https://challenges.cloudflare.com/cdn-cgi/x'), 'challenges.cloudflare.com')
  assert.equal(providerChallengeHost('https://sub.challenges.cloudflare.com/x'), 'challenges.cloudflare.com')
  assert.equal(providerChallengeHost('https://protect.clerk.com/x'), 'protect.clerk.com')
  assert.equal(providerChallengeHost('https://abc.protect.clerk.com/x'), 'protect.clerk.com')
  assert.equal(providerChallengeHost('https://challenges.cloudflare.com.evil.test/x'), null)
  assert.equal(providerChallengeHost('https://notchallenges.cloudflare.com/x'), null)
  assert.equal(providerChallengeHost('https://user:pass@challenges.cloudflare.com/x'), null)
  assert.equal(providerChallengeHost('http://challenges.cloudflare.com/x'), null)
  assert.equal(providerChallengeHost('about:blank'), null)
})

test('the dependency observation never carries raw URLs, queries or passwords', async () => {
  const password = 'Cr!9-super-secret'
  const credentialed = `https://user:${password}@challenges.cloudflare.com/cdn-cgi/challenge-platform?token=${password}`
  assert.equal(providerChallengeHost(credentialed), null)
  let observation
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => ({ target: false, challenge: 'challenges.cloudflare.com' }),
      timeoutMs: 1000,
      poll: fakePoll(2),
    }),
    error => { observation = error.observation; return true },
  )
  const serialized = JSON.stringify(observation)
  assert.ok(!serialized.includes(password))
  assert.ok(!serialized.includes('?token='))
  assert.ok(!/https?:|@/.test(serialized))
})

test('the founder email poll runs after the verification UI guard and write-ahead intents are preserved', async () => {
  const source = await readFile(new URL('../e2e/utils/ui-identity-campaign.js', import.meta.url), 'utf8')
  const guard = source.indexOf("stage: 'code'")
  const poll = source.indexOf("deliveredMail('admin'")
  assert.ok(guard > -1, 'the code-stage guard is present')
  assert.ok(poll > -1, 'the founder email poll is present')
  assert.ok(guard < poll, 'the verification UI guard runs before the founder email poll')
  assert.match(source, /provenance\.beginActorCreation\(email\)/)
  assert.match(source, /provenance\.beginOrganizationCreation\(\)/)
  assert.match(source, /provenance\.beginActorCreation\(teacherEmail\)/)
})

test('a thrown page read error propagates unchanged instead of becoming a timeout', async () => {
  const failure = new Error('page crashed')
  await assert.rejects(
    awaitAuthStage(fakePage({ readError: failure }), { stage: 'code', timeoutMs: 500 }),
    error => error === failure,
  )
})

test('a genuinely detached challenge frame is ignored during the passive poll', async () => {
  const frameError = new Error('frame detached')
  await assert.rejects(
    awaitAuthStage(fakePage({ challenge: 'https://challenges.cloudflare.com/x', frameError, detached: true }), { stage: 'code', timeoutMs: 200 }),
    error => error instanceof AuthStageTimeoutError && !(error instanceof AuthDependencyUnavailableError),
  )
})

test('an unrelated challenge frame error is preserved and never classified as a provider block', async () => {
  const frameError = new Error('frame read failed')
  await assert.rejects(
    awaitAuthStage(fakePage({ challenge: 'https://challenges.cloudflare.com/x', frameError, detached: false }), { stage: 'code', timeoutMs: 500 }),
    error => error === frameError,
  )
})

test('an invalid stage or bound fails before any read or external effect', async () => {
  let reads = 0
  const readState = async () => { reads += 1; return { target: true } }
  for (const stage of ['', 'signup', undefined, null]) {
    await assert.rejects(awaitAuthUi({ stage, readState, poll: fakePoll() }), error => error instanceof AuthStageConfigError)
  }
  for (const timeoutMs of [0, -1, NaN, Infinity, 120_001]) {
    await assert.rejects(awaitAuthUi({ stage: 'code', readState, timeoutMs, poll: fakePoll() }), error => error instanceof AuthStageConfigError)
  }
  for (const intervalMs of [0, -5, NaN, Infinity]) {
    await assert.rejects(awaitAuthUi({ stage: 'code', readState, intervalMs, poll: fakePoll() }), error => error instanceof AuthStageConfigError)
  }
  await assert.rejects(awaitAuthUi({ stage: 'code', readState: null, poll: fakePoll() }), error => error instanceof AuthStageConfigError)
  assert.equal(reads, 0)
  assert.equal(new AuthStageConfigError('stage').message, 'Invalid authentication stage configuration: stage')
})

test('a non-boolean truthy target can never report success', async () => {
  await assert.rejects(
    awaitAuthUi({ stage: 'code', readState: async () => ({ target: 'yes' }), timeoutMs: 1000, poll: fakePoll(3) }),
    error => error instanceof AuthStageTimeoutError,
  )
})

test('a provider block preserves the primary classification when the evidence attachment fails', async () => {
  const raw = new Error('attach failed for https://clerk.cronos.pt?password=fake-secret')
  const testInfo = { attach: async () => { throw raw } }
  await assert.rejects(
    awaitAuthStage(fakePage({ challenge: 'https://challenges.cloudflare.com/x' }), { stage: 'code', testInfo, timeoutMs: 50 }),
    error => {
      assert.ok(error instanceof AuthDependencyUnavailableError)
      assert.equal(error.code, 'auth_dependency_unavailable')
      assert.equal(error.cause?.code, 'auth_dependency_attachment_failed')
      assert.ok(!/fake-secret|\?password|https?:\/\//.test(`${error.message} ${error.cause?.message}`))
      return true
    },
  )
})

test('a never-settling read rejects within the provided bound instead of hanging', { timeout: 2000 }, async () => {
  const started = Date.now()
  await assert.rejects(
    awaitAuthUi({ stage: 'code', readState: () => new Promise(() => {}), timeoutMs: 20 }),
    error => error instanceof AuthStageTimeoutError,
  )
  assert.ok(Date.now() - started < 1000)
})

test('a target that resolves after the bound never reports success', { timeout: 2000 }, async () => {
  const gate = deferred()
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => { await gate.promise; return { target: true, challenge: null } },
      timeoutMs: 20,
    }),
    error => error instanceof AuthStageTimeoutError,
  )
  gate.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
})

test('a visible persistent challenge is classified from a completed read after the bound', async () => {
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => ({ target: false, challenge: 'challenges.cloudflare.com' }),
      timeoutMs: 50,
    }),
    error => error instanceof AuthDependencyUnavailableError && error.observation.challenge_host === 'challenges.cloudflare.com',
  )
})

test('a hung probe is never classified as a provider block from an older state', { timeout: 2000 }, async () => {
  const gate = deferred()
  let reads = 0
  await assert.rejects(
    awaitAuthUi({
      stage: 'code',
      readState: async () => {
        reads += 1
        if (reads > 1) await gate.promise
        return { target: false, challenge: 'challenges.cloudflare.com' }
      },
      timeoutMs: 60,
      intervalMs: 5,
    }),
    error => error instanceof AuthStageTimeoutError && !(error instanceof AuthDependencyUnavailableError),
  )
  gate.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
})

// Minimal route surface: page.route/unroute and route.request/fetch/fulfill.
function routedPage() {
  const page = { handlers: [], unrouted: [] }
  page.route = async (pattern, handler) => { page.handlers.push({ pattern, handler }) }
  page.unroute = async (pattern, handler) => { page.unrouted.push({ pattern, handler }) }
  return page
}

async function routeThrough(handler, url, body) {
  const seen = {}
  const response = { json: async () => { if (body === undefined) throw new Error('not json'); return structuredClone(body) } }
  await handler({
    request: () => ({ url: () => url }),
    fetch: async options => { seen.fetched = options; return response },
    fulfill: async options => { seen.fulfilled = options },
  })
  return seen
}

const TOKEN = 'tok_' + 'b'.repeat(40)

test('the sign-up testing token is scoped to the registration and always removed', async () => {
  const page = routedPage()
  await assert.rejects(withSignUpTestingToken(page, TOKEN, async () => { throw new Error('primary') }), /primary/)
  assert.equal(page.handlers.length, 1)
  assert.equal(page.handlers[0].pattern, 'https://clerk.cronos.pt/v1/**')
  assert.deepEqual(page.unrouted, [page.handlers[0]])
  for (const value of [undefined, '', 'short', 'has space'.repeat(5)]) {
    await assert.rejects(withSignUpTestingToken(routedPage(), value, async () => {}), /testing token/)
  }
})

test('the sign-up testing token only appends the parameter and lifts the captcha flag', async () => {
  const page = routedPage()
  await withSignUpTestingToken(page, TOKEN, async () => {})
  const { handler } = page.handlers[0]
  const client = await routeThrough(handler, 'https://clerk.cronos.pt/v1/client?_clerk_js_version=5', { response: { id: 'client_1', captcha_bypass: false } })
  const fetched = new URL(client.fetched.url)
  assert.equal(fetched.searchParams.get('__clerk_testing_token'), TOKEN)
  assert.equal(fetched.searchParams.get('_clerk_js_version'), '5')
  assert.equal(client.fulfilled.json.response.captcha_bypass, true)
  const piggyback = await routeThrough(handler, 'https://clerk.cronos.pt/v1/client/sign_ups', { response: { id: 'sua_1' }, client: { captcha_bypass: false } })
  assert.equal(piggyback.fulfilled.json.client.captcha_bypass, true)
  assert.equal(piggyback.fulfilled.json.response.id, 'sua_1')
  const environment = await routeThrough(handler, 'https://clerk.cronos.pt/v1/environment', { display_config: { captcha_widget_type: 'smart' } })
  assert.equal(environment.fulfilled.json, undefined)
  const binary = await routeThrough(handler, 'https://clerk.cronos.pt/v1/tickets/accept', undefined)
  assert.equal(binary.fulfilled.json, undefined)
  assert.ok(binary.fulfilled.response)
})

test('a poll read survives a navigation but never hides another page error', async () => {
  const navigating = { evaluate: async () => { throw new Error('page.evaluate: Execution context was destroyed, most likely because of a navigation') } }
  assert.equal(await evaluateAcrossNavigation(navigating, () => 1), undefined)
  const settled = { evaluate: async fn => fn() }
  assert.equal(await evaluateAcrossNavigation(settled, () => 'org_1'), 'org_1')
  const broken = { evaluate: async () => { throw new Error('page.evaluate: Target page, context or browser has been closed') } }
  await assert.rejects(evaluateAcrossNavigation(broken, () => 1), /has been closed/)
})

test('a request settled before the token route answers is left alone, other route errors are not', async () => {
  const page = routedPage()
  await withSignUpTestingToken(page, TOKEN, async () => {})
  const { handler } = page.handlers[0]
  const settled = { request: () => ({ url: () => 'https://clerk.cronos.pt/v1/client' }),
    fetch: async () => ({ json: async () => ({ response: { captcha_bypass: false } }) }),
    fulfill: async () => { throw new Error('route.fulfill: Route is already handled!') } }
  await handler(settled)
  const broken = { ...settled, fulfill: async () => { throw new Error('route.fulfill: unexpected') } }
  await assert.rejects(handler(broken), /unexpected/)
})

test('the sign-up token route lets a navigation such as an invitation ticket through untouched', async () => {
  const page = routedPage()
  await withSignUpTestingToken(page, TOKEN, async () => {})
  const { handler } = page.handlers[0]
  const seen = {}
  await handler({
    request: () => ({ url: () => 'https://clerk.cronos.pt/v1/tickets/accept?ticket=t', isNavigationRequest: () => true }),
    fetch: async () => { seen.fetched = true },
    fulfill: async () => { seen.fulfilled = true },
    continue: async () => { seen.continued = true },
  })
  assert.deepEqual(seen, { continued: true })
})

test('the authenticated stage keeps polling across a navigation', async () => {
  let reads = 0
  const page = fakePage({ target: true })
  page.evaluate = async () => {
    reads += 1
    if (reads === 1) throw new Error('page.evaluate: Execution context was destroyed, most likely because of a navigation')
    return true
  }
  await awaitAuthStage(page, { stage: 'authenticated', timeoutMs: 2000 })
  assert.ok(reads >= 2)
})
