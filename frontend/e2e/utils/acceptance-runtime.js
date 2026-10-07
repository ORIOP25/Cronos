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
