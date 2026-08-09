import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import worker from '../../worker/index.js'
const payload = { subject: 'Demonstração', courses: 'Entre 1 e 5', teachers: 'Entre 1 e 15', name: 'Ana Coordenadora', email: 'ana@escola.pt', phone: '+351 912 345 678', message: 'Mensagem', website: '', turnstileToken: 'token' }
const request = (data = payload) => new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
const env = (overrides = {}) => ({ TURNSTILE_SECRET_KEY: 'turnstile-secret', RESEND_API_KEY: 'resend-secret', CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: true }) }, ...overrides })

describe('contact Worker', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(async (url) => url === 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    ? new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'cronos.pt' }), { headers: { 'Content-Type': 'application/json' } })
    : new Response(null, { status: 202 }))))
  afterEach(() => vi.unstubAllGlobals())

  it('enforces route, method, content, JSON, allowed fields, and body size', async () => {
    const bindings = env()
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact'), bindings)).status).toBe(405)
    expect((await worker.fetch(new Request('https://cronos.pt/api/unknown'), bindings)).status).toBe(404)
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', body: '{}' }), bindings)).status).toBe(400)
    expect((await worker.fetch(new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{' }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, extra: true }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, message: 'x'.repeat(16 * 1024) }), bindings)).status).toBe(413)
  })

  it('checks payload boundaries and syntactically valid email', async () => {
    const bindings = env()
    for (const [field, max] of [['subject', 120], ['courses', 40], ['teachers', 40], ['name', 120], ['phone', 40], ['message', 3000], ['turnstileToken', 2048]]) expect((await worker.fetch(request({ ...payload, [field]: 'x'.repeat(max + 1) }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, subject: '' }), bindings)).status).toBe(400)
    expect((await worker.fetch(request({ ...payload, email: 'wrong' }), bindings)).status).toBe(400)
  })

  it('stops honeypots and rate limits before verification or email', async () => {
    expect((await worker.fetch(request({ ...payload, website: 'bot' }), env())).status).toBe(204)
    expect(fetch).not.toHaveBeenCalled()
    const limited = env({ CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: false }) } })
    const response = await worker.fetch(request(), limited)
    expect(response.status).toBe(429)
    expect(response.headers.get('Retry-After')).toBe('60')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('requires Turnstile success, contact action, and request hostname', async () => {
    const bindings = env()
    expect((await worker.fetch(request({ ...payload, turnstileToken: '' }), bindings)).status).toBe(400)
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ success: false })))
    expect((await worker.fetch(request(), bindings)).status).toBe(400)
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ success: true, action: 'other', hostname: 'cronos.pt' })))
    expect((await worker.fetch(request(), bindings)).status).toBe(400)
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'other.pt' })))
    expect((await worker.fetch(request(), bindings)).status).toBe(400)
  })

  it('sends one escaped Resend email after verification', async () => {
    expect((await worker.fetch(request({ ...payload, name: '<Ana>' }), env())).status).toBe(204)
    expect(fetch).toHaveBeenCalledTimes(2)
    const [url, options] = fetch.mock.calls.at(-1)
    expect(url).toBe('https://api.resend.com/emails')
    expect(options).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer resend-secret', 'Content-Type': 'application/json', 'User-Agent': 'cronos-website/1.0' } })
    expect(JSON.parse(options.body)).toMatchObject({
      from: 'Cronos Website <website@cronos.pt>', to: 'contacto@cronos.pt', reply_to: payload.email,
      subject: `[Cronos] Novo contacto \u2014 ${payload.subject}`,
      text: expect.stringContaining('<Ana>'), html: expect.stringContaining('&lt;Ana&gt;'),
    })
  })

  it('returns a safe 503 for missing secrets and Resend failures without logging submitted data', async () => {
    expect((await worker.fetch(request(), env({ RESEND_API_KEY: undefined }))).status).toBe(503)
    expect((await worker.fetch(request(), env({ TURNSTILE_SECRET_KEY: undefined }))).status).toBe(503)
    expect(fetch).not.toHaveBeenCalled()

    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'cronos.pt' }), { headers: { 'Content-Type': 'application/json' } }))
    fetch.mockImplementationOnce(async () => { throw new Error('failed') })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const response = await worker.fetch(request(), env())
    expect(response.status).toBe(503)
    expect((await response.json()).detail).toEqual(expect.any(String))
    expect(log).not.toHaveBeenCalledWith(expect.stringContaining(payload.name))
    log.mockRestore()

    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'cronos.pt' }), { headers: { 'Content-Type': 'application/json' } }))
    fetch.mockImplementationOnce(async () => new Response('unavailable', { status: 503 }))
    expect((await worker.fetch(request(), env())).status).toBe(503)
  })
})
