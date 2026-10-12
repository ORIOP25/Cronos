const DENIED_MESSAGE_PREFIX = 'TestNetworkDeniedError'

function denied(surface, detail) {
  const error = new Error(
    `${DENIED_MESSAGE_PREFIX}: unexpected ${surface} network request blocked by the unit-test guard (${detail})`,
  )
  error.name = DENIED_MESSAGE_PREFIX
  return error
}

function describeFetch(input, init) {
  const url = typeof input === 'string' ? input : input?.url
  const method = init?.method ?? input?.method ?? 'GET'
  return `${method} ${url}`
}

// Replaces the jsdom transports with a fail-closed denial. Tests that mock their
// network layer (vi.mock / vi.stubGlobal) never hit this. Any accidental real
// request throws a classified error instead of reaching an external host.
export function installNetworkDeny(target) {
  const originalFetch = target.fetch
  const Xhr = target.XMLHttpRequest
  const originalOpen = Xhr?.prototype?.open
  const originalSend = Xhr?.prototype?.send

  if (typeof originalFetch === 'function') {
    target.fetch = (input, init) => {
      throw denied('fetch', describeFetch(input, init))
    }
  }
  if (typeof originalOpen === 'function') {
    Xhr.prototype.open = function open(method, url) {
      throw denied('XMLHttpRequest', `${method} ${url}`)
    }
  }
  if (typeof originalSend === 'function') {
    Xhr.prototype.send = function send() {
      throw denied('XMLHttpRequest', 'send without a guarded open')
    }
  }

  return () => {
    if (typeof originalFetch === 'function') target.fetch = originalFetch
    if (typeof originalOpen === 'function') Xhr.prototype.open = originalOpen
    if (typeof originalSend === 'function') Xhr.prototype.send = originalSend
  }
}
