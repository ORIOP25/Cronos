import { getApiResponseError, getConsoleError, getOptionalTelemetryResponseError, getRequestFailureError, isOptionalTelemetryScriptUrl, optionalTelemetryScriptFromConsoleText } from './runtime-guards.js'

let activityObserver = null

// The acceptance proof adapter subscribes once per test. Every observed page
// navigation or request counts as a real UI/page action for checkpoint provenance.
export function observeAcceptanceActivity(observer) {
  activityObserver = observer
}

function requestResourceType(request) {
  try { return typeof request.resourceType === 'function' ? request.resourceType() : '' } catch { return '' }
}

function requestMethod(request) {
  try { return typeof request.method === 'function' ? String(request.method()).toUpperCase() : '' } catch { return '' }
}

// An unexpected Clerk failure keeps only Clerk's fixed error codes, never its
// messages, so a provider rejection is diagnosable from the safe evidence.
async function clerkErrorCodes(response) {
  try {
    const body = await response.json()
    return (body?.errors || []).map(item => item?.code).filter(code => /^[a-z0-9_]{1,64}$/.test(code || ''))
  } catch { return [] }
}

function isExpectedFailure(observed, allowed) {
  const url = new URL(observed.url)
  return allowed.some(item => item.origin === url.origin && item.pathname === url.pathname
    && item.method === observed.method && item.status === observed.status)
}

export function observeAcceptanceRuntime(page) {
  const confirmedErrors = []
  const requests = new WeakMap()
  const failedResponses = new Map()
  const optionalTelemetry = new Set()
  // Chrome can emit the CSP console message before the network events. Keep
  // every exact candidate per URL as an unresolved error until the later
  // observed script GET + CSP failure verifies the same URL.
  const pendingCspConsoles = new Map()
  const ignoredOptionalTelemetry = []
  const baseUrl = 'https://cronos.pt'
  let current = { action: null, allowed: [] }
  const record = error => { if (error) confirmedErrors.push(error) }
  const activity = () => { activityObserver?.() }
  const noteIgnoredOptionalTelemetry = diagnostic => { ignoredOptionalTelemetry.push(diagnostic) }
  const pendingConsoleError = entry => `Browser console error: ${entry.message.text} at ${entry.message.locationUrl}`
  const flushPendingConsole = url => {
    const entries = pendingCspConsoles.get(url)
    if (!entries) return
    pendingCspConsoles.delete(url)
    for (const entry of entries) confirmedErrors.push(pendingConsoleError(entry))
  }
  const reconcilePendingConsole = url => {
    const entries = pendingCspConsoles.get(url)
    if (!entries) return
    // Reuse the existing classifier: with the observation now present each
    // verified entry suppresses and emits its safe console diagnostic.
    const unresolved = entries.filter(entry => getConsoleError(entry.message, entry.allowed, {
      baseUrl, action: entry.action, observedOptionalTelemetry: optionalTelemetry, onIgnoredOptionalTelemetry: noteIgnoredOptionalTelemetry,
    }) !== null)
    if (unresolved.length) pendingCspConsoles.set(url, unresolved)
    else pendingCspConsoles.delete(url)
  }
  const listeners = {
    request(request) {
      activity()
      const url = request.url()
      requests.set(request, current)
      failedResponses.delete(url)
      const isBeaconScriptGet = requestResourceType(request) === 'script'
        && requestMethod(request) === 'GET'
        && isOptionalTelemetryScriptUrl(url)
      // A new non-beacon request at this URL invalidates and confirms any
      // pending candidate. A known script GET preserves it for reconciliation.
      if (!isBeaconScriptGet) flushPendingConsole(url)
      optionalTelemetry.delete(url)
      if (isBeaconScriptGet) optionalTelemetry.add(url)
    },
    framenavigated(frame) {
      activity()
      // A subframe navigation must not discard the current document state; only
      // a main-frame navigation flushes pending candidates and invalidates.
      const isMainFrame = !frame
        || (typeof frame.parentFrame === 'function' ? frame.parentFrame() === null : frame === page.mainFrame?.())
      if (isMainFrame) {
        for (const url of [...pendingCspConsoles.keys()]) flushPendingConsole(url)
        optionalTelemetry.clear()
      }
    },
    pageerror(error) { record(`Browser exception: ${error.message}`) },
    requestfailed(request) {
      const url = request.url()
      let verifiedOptionalTelemetry = false
      const error = getRequestFailureError({
        url,
        method: request.method(),
        resourceType: requestResourceType(request),
        errorText: request.failure()?.errorText,
      }, {
        baseUrl,
        observedOptionalTelemetry: optionalTelemetry,
        onIgnoredOptionalTelemetry: diagnostic => { verifiedOptionalTelemetry = true; noteIgnoredOptionalTelemetry(diagnostic) },
      })
      if (verifiedOptionalTelemetry) {
        // Causal reconciliation: this later script GET + CSP failure verifies
        // the earlier console candidate for the exact same full URL.
        reconcilePendingConsole(url)
        return
      }
      // Any other network outcome confirms unresolved candidates first.
      flushPendingConsole(url)
      record(error)
    },
    response(response) {
      const request = response.request()
      const status = Number(response.status())
      // Checked before invalidation: a served beacon 4xx/5xx must stay an error
      // even when no console message follows.
      const servedBeaconError = getOptionalTelemetryResponseError({ url: request.url(), status }, optionalTelemetry)
      flushPendingConsole(request.url())
      // A real HTTP response proves the request was served, not CSP-blocked.
      // Any later CSP-looking console or failure must not reuse a prior
      // observation, so a beacon 4xx/5xx can never be masked as optional.
      optionalTelemetry.delete(response.url())
      optionalTelemetry.delete(request.url())
      const scope = requests.get(request) ?? { action: null, allowed: [] }
      const observed = { url: response.url(), method: request.method(), status: response.status() }
      if (observed.status >= 400) failedResponses.set(observed.url, { ...observed, scope })
      if (observed.status >= 400 && new URL(observed.url).origin === 'https://clerk.cronos.pt' && !isExpectedFailure(observed, scope.allowed)) {
        void clerkErrorCodes(response).then(codes => record(`Clerk ${observed.status} ${observed.method} ${new URL(observed.url).pathname}: ${codes.join(',') || 'no_code'}`))
      }
      record(servedBeaconError)
      record(getApiResponseError(observed, scope.allowed, { baseUrl, action: scope.action }))
    },
    console(message) {
      const text = message.text()
      const locationUrl = message.location()?.url ?? ''
      const failed = failedResponses.get(locationUrl)
      const scope = failed?.scope ?? { action: null, allowed: [] }
      const consoleMessage = { type: message.type(), text, locationUrl, method: failed?.method }
      const candidateUrl = message.type() === 'error' ? optionalTelemetryScriptFromConsoleText(text) : null
      if (candidateUrl && isOptionalTelemetryScriptUrl(candidateUrl) && !optionalTelemetry.has(candidateUrl)) {
        const entries = pendingCspConsoles.get(candidateUrl) ?? []
        entries.push({ message: consoleMessage, allowed: scope.allowed, action: scope.action })
        pendingCspConsoles.set(candidateUrl, entries)
        return
      }
      record(getConsoleError(consoleMessage, scope.allowed, {
        baseUrl, action: scope.action, observedOptionalTelemetry: optionalTelemetry, onIgnoredOptionalTelemetry: noteIgnoredOptionalTelemetry,
      }))
    },
  }
  for (const [name, listener] of Object.entries(listeners)) page.on(name, listener)
  return {
    // Confirmed errors plus still-unresolved CSP console candidates. An unknown
    // or stale candidate always stays visibly failing until causally verified.
    get errors() {
      return [...confirmedErrors, ...[...pendingCspConsoles.values()].flatMap(entries => entries.map(pendingConsoleError))]
    },
    ignoredOptionalTelemetry,
    allowRequestFailure(request, status) {
      if (!current.action || requests.get(request) !== current || !Number.isInteger(status) || status < 400 || status >= 500) {
        record('Expected failure registration requires an observed request in its initiating action and a 4xx status')
        return false
      }
      let url
      try { url = new URL(request.url()) } catch {
        record('Expected failure registration requires a valid request URL')
        return false
      }
      if (!['https://cronos.pt', 'https://api.cronos.pt', 'https://clerk.cronos.pt'].includes(url.origin)) {
        record('Expected failure registration requires a production application origin')
        return false
      }
      requests.set(request, { action: current.action, allowed: [...current.allowed, {
        origin: url.origin, pathname: url.pathname, method: request.method(), status, action: current.action,
      }] })
      return true
    },
    async action(name, allowed, perform) {
      const previous = current
      current = { action: name, allowed: [...allowed] }
      try { return await perform() } finally { current = previous }
    },
    dispose() {
      for (const [name, listener] of Object.entries(listeners)) page.off(name, listener)
    },
  }
}
