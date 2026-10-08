import { getApiResponseError, getConsoleError, getRequestFailureError } from './runtime-guards.js'

export function observeAcceptanceRuntime(page) {
  const errors = []
  const requests = new WeakMap()
  const failedResponses = new Map()
  const baseUrl = 'https://cronos.pt'
  let current = { action: null, allowed: [] }
  const record = error => { if (error) errors.push(error) }
  const listeners = {
    request(request) {
      requests.set(request, current)
      failedResponses.delete(request.url())
    },
    pageerror(error) { record(`Browser exception: ${error.message}`) },
    requestfailed(request) {
      record(getRequestFailureError({ url: request.url(), method: request.method(), errorText: request.failure()?.errorText }, { baseUrl }))
    },
    response(response) {
      const request = response.request()
      const scope = requests.get(request) ?? { action: null, allowed: [] }
      const observed = { url: response.url(), method: request.method(), status: response.status() }
      if (observed.status >= 400) failedResponses.set(observed.url, { ...observed, scope })
      record(getApiResponseError(observed, scope.allowed, { baseUrl, action: scope.action }))
    },
    console(message) {
      const url = message.location()?.url ?? ''
      const failed = failedResponses.get(url)
      const scope = failed?.scope ?? { action: null, allowed: [] }
      record(getConsoleError({ type: message.type(), text: message.text(), locationUrl: url, method: failed?.method }, scope.allowed, { baseUrl, action: scope.action }))
    },
  }
  for (const [name, listener] of Object.entries(listeners)) page.on(name, listener)
  return {
    errors,
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
