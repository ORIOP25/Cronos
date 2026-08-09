import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import worker from '../../worker/index.js'

const payload = { subject: 'Demonstração', courses: 'Entre 1 e 5', teachers: 'Entre 1 e 15', name: 'Ana Coordenadora', email: 'ana@escola.pt', phone: '+351 912 345 678', message: 'Mensagem', website: '', turnstileToken: 'token' }
const request = (data = payload) => new Request('https://cronos.pt/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
const env = (overrides = {}) => ({ TURNSTILE_SECRET_KEY: 'secret', CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: true }) }, CONTACT_EMAIL: { send: vi.fn().mockResolvedValue({ messageId: 'id' }) }, ...overrides })

describe('contact Worker', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: true, action: 'contact', hostname: 'cronos.pt' }), { headers: { 'Content-Type': 'application/json' } })))
  })
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
    const honeypot = env()
    expect((await worker.fetch(request({ ...payload, website: 'bot' }), honeypot)).status).toBe(204)
    expect(fetch).not.toHaveBeenCalled()
    const limited = env({ CONTACT_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success: false }) } })
    const response = await worker.fetch(request(), limited)
    expect(response.status).toBe(429)
    expect(response.headers.get('Retry-After')).toBe('60')
    expect(limited.CONTACT_EMAIL.send).not.toHaveBeenCalled()
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

  it('sends escaped email after verification and returns a safe delivery error', async () => {
    const bindings = env()
    expect((await worker.fetch(request({ ...payload, name: '<Ana>' }), bindings)).status).toBe(204)
    expect(bindings.CONTACT_EMAIL.send).toHaveBeenCalledWith(expect.objectContaining({ from: { name: 'Cronos Website', email: 'website@cronos.pt' }, to: 'contacto@cronos.pt', replyTo: 'ana@escola.pt', subject: '[Cronos] Novo contacto — Demonstração', html: expect.stringContaining('&lt;Ana&gt;') }))
    const failed = env({ CONTACT_EMAIL: { send: vi.fn().mockRejectedValue(new Error('failed')) } })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const response = await worker.fetch(request(), failed)
    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({ detail: 'Não foi possível enviar o pedido neste momento.' })
    expect(log).not.toHaveBeenCalledWith(expect.stringContaining(payload.name))
    log.mockRestore()
  })
})
