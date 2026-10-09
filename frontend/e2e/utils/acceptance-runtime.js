import { getApiResponseError, getConsoleError, getOptionalTelemetryResponseError, getRequestFailureError, isOptionalTelemetryScriptUrl } from './runtime-guards.js'

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

export function observeAcceptanceRuntime(page) {
  const errors = []
  const requests = new WeakMap()
  const failedResponses = new Map()
  const optionalTelemetry = new Set()
  const ignoredOptionalTelemetry = []
  const baseUrl = 'https://cronos.pt'
  let current = { action: null, allowed: [] }
  const record = error => { if (error) errors.push(error) }
  const activity = () => { activityObserver?.() }
  const noteIgnoredOptionalTelemetry = diagnostic => { ignoredOptionalTelemetry.push(diagnostic) }
  const listeners = {
    request(request) {
      activity()
      requests.set(request, current)
      failedResponses.delete(request.url())
      // A fresh request at the same URL replaces any prior optional telemetry
      // observation, and a non-script or non-GET request invalidates it. This is
      // a scoped observation, never a global allowlist of the URL.
      optionalTelemetry.delete(request.url())
      if (
        requestResourceType(request) === 'script'
        && requestMethod(request) === 'GET'
        && isOptionalTelemetryScriptUrl(request.url())
      ) {
        optionalTelemetry.add(request.url())
      }
    },
    framenavigated(frame) {
      activity()
      // A subframe navigation must not discard the top document's observation;
      // only a main-frame navigation invalidates it. A missing frame stays main
      // for the event-emitter test doubles.
      const isMainFrame = !frame
        || (typeof frame.parentFrame === 'function' ? frame.parentFrame() === null : frame === page.mainFrame?.())
      if (isMainFrame) optionalTelemetry.clear()
    },
    pageerror(error) { record(`Browser exception: ${error.message}`) },
    requestfailed(request) {
      record(getRequestFailureError({
        url: request.url(),
        method: request.method(),
        resourceType: requestResourceType(request),
        errorText: request.failure()?.errorText,
      }, { baseUrl, observedOptionalTelemetry: optionalTelemetry, onIgnoredOptionalTelemetry: noteIgnoredOptionalTelemetry }))
    },
    response(response) {
      const request = response.request()
      const status = Number(response.status())
      // Checked before invalidation: a served beacon 4xx/5xx must stay an error
      // even when no console message follows.
      record(getOptionalTelemetryResponseError({ url: request.url(), status }, optionalTelemetry))
      // A real HTTP response proves the request was served, not CSP-blocked.
      // Any later CSP-looking console or failure must not reuse a prior
      // observation, so a beacon 4xx/5xx can never be masked as optional.
      optionalTelemetry.delete(response.url())
      optionalTelemetry.delete(request.url())
      const scope = requests.get(request) ?? { action: null, allowed: [] }
      const observed = { url: response.url(), method: request.method(), status: response.status() }
      if (observed.status >= 400) failedResponses.set(observed.url, { ...observed, scope })
      record(getApiResponseError(observed, scope.allowed, { baseUrl, action: scope.action }))
    },
    console(message) {
      const url = message.location()?.url ?? ''
      const failed = failedResponses.get(url)
      const scope = failed?.scope ?? { action: null, allowed: [] }
      record(getConsoleError({ type: message.type(), text: message.text(), locationUrl: url, method: failed?.method }, scope.allowed, {
        baseUrl, action: scope.action, observedOptionalTelemetry: optionalTelemetry, onIgnoredOptionalTelemetry: noteIgnoredOptionalTelemetry,
      }))
    },
  }
  for (const [name, listener] of Object.entries(listeners)) page.on(name, listener)
  return {
    errors,
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
