const MAX_BODY_BYTES = 16 * 1024
const ALLOWED_FIELDS = new Set(['subject', 'courses', 'teachers', 'name', 'email', 'phone', 'message', 'website', 'turnstileToken'])
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function json(detail, status, headers = {}) {
  return new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers } })
}

function noContent() {
  return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } })
}

async function readLimitedBody(request) {
  const length = Number(request.headers.get('Content-Length'))
  if (Number.isFinite(length) && length > MAX_BODY_BYTES) return null
  const reader = request.body?.getReader()
  if (!reader) return ''
  const chunks = []
  let size = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    size += value.byteLength
    if (size > MAX_BODY_BYTES) {
      await reader.cancel()
      return null
    }
    chunks.push(value)
  }
  const body = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength }
  return new TextDecoder().decode(body)
}

function text(value, field, maximum, required = false) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  if ((required && !normalized) || normalized.length > maximum) return null
  if (field === 'subject' && /[\r\n]/.test(normalized)) return null
  return normalized
}

function validate(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).some((field) => !ALLOWED_FIELDS.has(field))) return null
  const subject = text(payload.subject, 'subject', 120, true)
  const courses = text(payload.courses, 'courses', 40, true)
  const teachers = text(payload.teachers, 'teachers', 40, true)
  const name = text(payload.name, 'name', 120, true)
  const email = text(payload.email, 'email', 254, true)
  const phone = text(payload.phone ?? '', 'phone', 40)
  const message = text(payload.message ?? '', 'message', 3000)
  const website = text(payload.website, 'website', 120)
  const turnstileToken = text(payload.turnstileToken, 'turnstileToken', 2048, true)
  if ([subject, courses, teachers, name, email, phone, message, website, turnstileToken].some((value) => value == null) || !EMAIL_PATTERN.test(email)) return null
  return { subject, courses, teachers, name, email, phone, message, website, turnstileToken }
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character])
}

function emailBodies(data) {
  const values = [
    ['Nome', data.name], ['Email', data.email], ['Telefone', data.phone || 'Não indicado'], ['Assunto', data.subject], ['Cursos', data.courses], ['Professores', data.teachers], ['Mensagem', data.message || 'Não indicada'],
  ]
  return {
    text: values.map(([label, value]) => `${label}: ${value}`).join('\n'),
    html: `<h1>Novo contacto Cronos</h1><dl>${values.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl>`,
  }
}

async function verifyTurnstile(token, hostname, env) {
  try {
    const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ secret: env.TURNSTILE_SECRET_KEY, response: token }),
    })
    const result = await response.json()
    return result.success === true && result.action === 'contact' && result.hostname === hostname
  } catch {
    return false
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    if (url.pathname !== '/api/contact') return json('Rota não encontrada.', 404)
    if (request.method !== 'POST') return json('Método não permitido.', 405, { Allow: 'POST' })
    if (!request.headers.get('Content-Type')?.toLowerCase().startsWith('application/json')) return json('Pedido inválido.', 400)

    const raw = await readLimitedBody(request)
    if (raw == null) return json('Pedido demasiado grande.', 413)
    let payload
    try { payload = JSON.parse(raw) } catch { return json('Pedido inválido.', 400) }
    const data = validate(payload)
    if (!data) return json('Pedido inválido.', 400)
    if (data.website) return noContent()
    if (!env.TURNSTILE_SECRET_KEY || !env.RESEND_API_KEY) return json('Não foi possível enviar o pedido neste momento.', 503)

    const { success } = await env.CONTACT_RATE_LIMITER.limit({ key: `contact:${request.headers.get('CF-Connecting-IP') || 'unknown'}` })
    if (!success) return json('Foram efetuadas várias tentativas. Aguarde e tente novamente.', 429, { 'Retry-After': '60' })
    if (!await verifyTurnstile(data.turnstileToken, url.hostname, env)) return json('A verificação anti-spam falhou. Tente novamente.', 400)

    try {
      const bodies = emailBodies(data)
      const response = await fetch('https://api.resend.com/emails', { method: 'POST', headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json', 'User-Agent': 'cronos-website/1.0' }, body: JSON.stringify({ from: 'Cronos Website <website@cronos.pt>', to: 'contacto@cronos.pt', reply_to: data.email, subject: `[Cronos] Novo contacto \u2014 ${data.subject}`, ...bodies }) })
      if (!response.ok) throw new Error('Resend request failed')
      return noContent()
    } catch {
      console.error('Contact email sending failed')
      return json('Não foi possível enviar o pedido neste momento.', 503)
    }
  },
}
