import { describe, expect, it, vi } from 'vitest'
import { installNetworkDeny } from './networkGuard'

function fakeTransport() {
  const fetchSentinel = vi.fn(() => 'sent')
  const xhrSendSentinel = vi.fn()
  class FakeXhr {
    open() {}
    send() { xhrSendSentinel() }
  }
  return { target: { fetch: fetchSentinel, XMLHttpRequest: FakeXhr }, fetchSentinel, xhrSendSentinel, FakeXhr }
}

describe('DOM fail-closed network guard', () => {
  it('reaches the controlled transport without the guard and blocks it with the guard (fetch)', () => {
    const { target, fetchSentinel } = fakeTransport()

    // RED evidence: without the guard the request would reach the transport.
    expect(target.fetch('https://example.invalid/unhandled')).toBe('sent')
    expect(fetchSentinel).toHaveBeenCalledTimes(1)

    fetchSentinel.mockClear()
    const restore = installNetworkDeny(target)

    // GREEN: the guard throws a classified error and never touches the transport.
    expect(() => target.fetch('https://example.invalid/unhandled')).toThrowError(/TestNetworkDeniedError/)
    expect(fetchSentinel).not.toHaveBeenCalled()

    restore()
    expect(target.fetch('https://example.invalid/unhandled')).toBe('sent')
  })

  it('reaches the controlled transport without the guard and blocks it with the guard (XHR)', () => {
    const { target, xhrSendSentinel, FakeXhr } = fakeTransport()

    // RED evidence: an unhandled XHR still sends without the guard.
    const withoutGuard = new FakeXhr()
    withoutGuard.open('POST', 'https://example.invalid/unhandled')
    withoutGuard.send()
    expect(xhrSendSentinel).toHaveBeenCalledTimes(1)

    xhrSendSentinel.mockClear()
    const restore = installNetworkDeny(target)

    // GREEN: opening a request is denied before send can happen.
    const guarded = new FakeXhr()
    expect(() => guarded.open('POST', 'https://example.invalid/unhandled')).toThrowError(/TestNetworkDeniedError/)
    expect(xhrSendSentinel).not.toHaveBeenCalled()

    restore()
  })

  it('is active on the real DOM environment every unguarded test file runs in', () => {
    expect(() => globalThis.fetch('https://example.invalid/unhandled')).toThrowError(/TestNetworkDeniedError/)
    expect(() => new XMLHttpRequest().open('GET', 'https://example.invalid/unhandled')).toThrowError(/TestNetworkDeniedError/)
  })
})
