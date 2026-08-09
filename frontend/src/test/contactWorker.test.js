import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import worker from '../../worker/index.js'

const payload = { subject: 'Demonstra\u00e7\u00e3o', courses: 'Entre 1 e 5', teachers: 'Entre 1 e 15', name: 'Ana Coordenadora', email: 'ana@escola.pt', phone: '+351 912 345 678', message: 'Mensagem', website: '', turnstileToken: 'token' }
const request = (data = payload, options = {}) => new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json', ...options.headers }, body: JSON.stringify(data), ...options })
const env = (overrides = {}) => ({ TURNSTILE_SECRET_KEY: 'turnstile-secret', CONTACT_EMAIL: { send: vi.fn().mockResolvedValue(undefined) }, CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: true }) }, ...overrides })

describe('contact Worker', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'cronos.pt' }), { headers: { 'Content-Type': 'application/json' } }))))
  afterEach(() => vi.unstubAllGlobals())

  it('enforces routes, methods, payloads, and body limits', async () => {
    const bindings = env()
    const method = await worker.fetch(new Request('https://cronos.pt/api/contact'), bindings)
    expect(method.status).toBe(405); expect(method.headers.get('Allow')).toBe('POST')
    expect((await worker.fetch(new Request('https://cronos.pt/api/unknown'), bindings)).status).toBe(404)
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', body: '{}' }), bindings)).status).toBe(400)
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{' }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, extra: true }), bindings)).status).toBe(400)
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': String(16 * 1024 + 1) }, body: JSON.stringify(payload) }), bindings)).status).toBe(413)
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('x'.repeat(16 * 1024 + 1))); controller.close() } })
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, duplex: 'half' }), bindings)).status).toBe(413)
  })

  it('validates mandatory values, boundaries, email, and subject lines', async () => {
    const bindings = env()
    for (const [field, max] of [['subject', 120], ['courses', 40], ['teachers', 40], ['name', 120], ['phone', 40], ['message', 3000], ['turnstileToken', 2048]]) {
      expect((await worker.fetch(request({ ...payload, [field]: 'x'.repeat(max) }), bindings)).status).toBe(204)
      expect((await worker.fetch(request({ ...payload, [field]: 'x'.repeat(max + 1) }), bindings)).status).toBe(400)
    }
    const email = `${'a'.repeat(242)}@example.com`
    expect((await worker.fetch(request({ ...payload, email }), bindings)).status).toBe(204)
    expect((await worker.fetch(request({ ...payload, email: `${email}x` }), bindings)).status).toBe(400)
    for (const field of ['subject', 'courses', 'teachers', 'name', 'email', 'turnstileToken']) expect((await worker.fetch(request({ ...payload, [field]: '' }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, email: 'wrong' }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, subject: 'Hello\nBcc: x' }), bindings)).status).toBe(400)
  })

  it('silently stops honeypots before limiting, Turnstile, or delivery', async () => {
    const bindings = env()
    expect((await worker.fetch(request({ ...payload, website: 'bot' }), bindings)).status).toBe(204)
    expect(bindings.CONTACT_RATE_LIMITER.limit).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled(); expect(bindings.CONTACT_EMAIL.send).not.toHaveBeenCalled()
  })

  it('rate limits before Turnstile verification', async () => {
    const bindings = env({ CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: false }) } })
    const response = await worker.fetch(request(), bindings)
    expect(response.status).toBe(429); expect(response.headers.get('Retry-After')).toBe('60'); expect(fetch).not.toHaveBeenCalled()
  })

  it('requires correct Turnstile success, action, and hostname', async () => {
    const bindings = env()
    for (const result of [{ success: false }, { success: true, action: 'other', hostname: 'cronos.pt' }, { success: true, action: 'contact', hostname: 'other.pt' }]) {
      fetch.mockResolvedValueOnce(new Response(JSON.stringify(result)))
      expect((await worker.fetch(request(), bindings)).status).toBe(400)
    }
  })

  it('requires native email bindings before processing', async () => {
    expect((await worker.fetch(request(), env({ TURNSTILE_SECRET_KEY: undefined }))).status).toBe(503)
    expect((await worker.fetch(request(), env({ CONTACT_EMAIL: undefined }))).status).toBe(503)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('sends exactly one escaped native email after verification', async () => {
    const bindings = env()
    expect((await worker.fetch(request({ ...payload, name: '<Ana>' }), bindings)).status).toBe(204)
    expect(fetch).toHaveBeenCalledTimes(1); expect(bindings.CONTACT_EMAIL.send).toHaveBeenCalledTimes(1)
    expect(bindings.CONTACT_EMAIL.send).toHaveBeenCalledWith(expect.objectContaining({
      from: { name: 'Cronos Website', email: 'website@forms.cronos.pt' }, to: 'contacto@cronos.pt', replyTo: payload.email,
      subject: expect.stringContaining(payload.subject), text: expect.stringContaining('<Ana>'), html: expect.stringContaining('&lt;Ana&gt;'),
    }))
  })

  it('returns a safe 503 for delivery failure without logging submitted data', async () => {
    const bindings = env({ CONTACT_EMAIL: { send: vi.fn().mockRejectedValue(new Error('failed')) } })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const response = await worker.fetch(request(), bindings)
    expect(response.status).toBe(503); expect((await response.json()).detail).toEqual(expect.any(String))
    expect(log).not.toHaveBeenCalledWith(expect.stringContaining(payload.name)); log.mockRestore()
  })
})