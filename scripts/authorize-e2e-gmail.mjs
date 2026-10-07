import { createHash, randomBytes, timingSafeEqual } from 'node:crypto'
import { createServer } from 'node:http'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const MAILBOXES = { admin: 'admincronos100@gmail.com', teacher: 'professorcronos100@gmail.com' }

export function createAuthorization(clientId, redirectUri, mailbox) {
  if (!clientId || !Object.values(MAILBOXES).includes(mailbox)) throw new Error('Dedicated Gmail client and mailbox required')
  const redirect = new URL(redirectUri)
  if (redirect.protocol !== 'http:' || redirect.hostname !== '127.0.0.1' || redirect.pathname !== '/callback' || redirect.username || redirect.password) throw new Error('OAuth requires a loopback callback')
  const state = randomBytes(32).toString('base64url')
  const verifier = randomBytes(32).toString('base64url')
  const params = new URLSearchParams({
    client_id: clientId, redirect_uri: redirect.href, response_type: 'code',
    scope: 'https://www.googleapis.com/auth/gmail.readonly', access_type: 'offline', prompt: 'consent',
    state, code_challenge: createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256', login_hint: mailbox,
  })
  return { url: `https://accounts.google.com/o/oauth2/v2/auth?${params}`, state, verifier }
}

export function validateCallback(requestUrl, state) {
  const url = new URL(requestUrl, 'http://127.0.0.1')
  const received = Buffer.from(url.searchParams.get('state') || '')
  const expected = Buffer.from(state)
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.username || url.password || url.hash || url.pathname !== '/callback'
    || url.searchParams.getAll('state').length !== 1 || url.searchParams.getAll('code').length !== 1
    || !expected.length || received.length !== expected.length || !timingSafeEqual(received, expected)
    || !url.searchParams.get('code') || url.searchParams.has('error')) throw new Error('Invalid OAuth callback')
  return url.searchParams.get('code')
}

async function authorize(actor, environment) {
  const mailbox = MAILBOXES[actor]
  const clientId = environment.E2E_GMAIL_CLIENT_ID
  const clientSecret = environment.E2E_GMAIL_CLIENT_SECRET
  if (!mailbox || !clientId || !clientSecret) throw new Error('Use admin or teacher and configure OAuth Desktop credentials')
  const server = createServer()
  await new Promise((accept, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', accept) })
  const redirectUri = `http://127.0.0.1:${server.address().port}/callback`
  const auth = createAuthorization(clientId, redirectUri, mailbox)
  try {
    // No browser opens automatically; the caller selects its isolated browser.
    console.log(`Consent URL for ${mailbox}:\n${auth.url}`)
    const code = await new Promise((accept, reject) => {
      const timer = setTimeout(() => reject(new Error('OAuth consent deadline exceeded')), 300_000)
      server.on('request', (request, response) => {
        try {
          if (request.method !== 'GET') throw new Error('Invalid OAuth callback method')
          const received = validateCallback(request.url, auth.state)
          clearTimeout(timer)
          response.writeHead(200, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }); response.end('Consent received. You can close this tab.')
          accept(received)
        } catch {
          response.writeHead(400, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }); response.end('Invalid consent callback.')
        }
      })
    })
    const response = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15_000),
      body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, code, code_verifier: auth.verifier, redirect_uri: redirectUri, grant_type: 'authorization_code' }),
    })
    if (!response.ok) throw new Error(`OAuth token exchange failed: HTTP ${response.status}`)
    const result = await response.json()
    if (!result.refresh_token || result.scope !== 'https://www.googleapis.com/auth/gmail.readonly') throw new Error('Readonly offline consent was not granted')
    const profile = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/profile', { headers: { Authorization: `Bearer ${result.access_token}` }, redirect: 'error', signal: AbortSignal.timeout(15_000) })
    if (!profile.ok || (await profile.json()).emailAddress?.toLowerCase() !== mailbox) throw new Error('Consent mailbox does not match the dedicated account')
    await new Promise((accept, reject) => {
      const child = spawn('gh', ['secret', 'set', `E2E_GMAIL_${actor.toUpperCase()}_REFRESH_TOKEN`, '--repo', 'ORIOP25/Cronos'], { stdio: ['pipe', 'ignore', 'ignore'], shell: false, windowsHide: true })
      child.once('error', reject)
      child.once('exit', code => code === 0 ? accept() : reject(new Error('Secure refresh token transfer failed')))
      child.stdin.on('error', reject)
      child.stdin.end(result.refresh_token)
    })
    console.log(`Readonly Gmail consent stored for ${actor}. No token was printed.`)
  } finally {
    server.closeAllConnections()
    await new Promise(accept => server.close(accept))
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { await authorize(process.argv[2], process.env) } catch (error) { console.error(error.message); process.exitCode = 1 }
}
