/**
 * Clerk Testing Tokens — Cache e reutilização.
 *
 * Usado pelos E2E com Clerk real. Gera tokens JWT válidos via BAPI
 * e injeta-os como cookie __session para autenticação same-origin.
 *
 * Taxa: 2 chamadas à BAPI para TODOS os cenários (admin + teacher).
 * Zero risco de rate limit (100 req/10s em dev).
 */

let _adminToken = null
let _teacherToken = null

const CLERK_API = 'https://api.clerk.com/v1/testing_tokens'
const SECRET_KEY = process.env.CLERK_SECRET_KEY || ''

async function createToken() {
  if (!SECRET_KEY) {
    throw new Error('CLERK_SECRET_KEY não definida. Define no .env ou GitHub Secrets.')
  }
  const res = await fetch(CLERK_API, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${SECRET_KEY}`,
      'Content-Type': 'application/json',
    },
  })
  if (!res.ok) {
    throw new Error(`Clerk testing_tokens falhou: ${res.status} ${await res.text()}`)
  }
  const data = await res.json()
  return data.token
}

export async function getOrCreateAdminToken() {
  if (!_adminToken) {
    _adminToken = await createToken()
  }
  return _adminToken
}

export async function getOrCreateTeacherToken() {
  if (!_teacherToken) {
    _teacherToken = await createToken()
  }
  return _teacherToken
}

export function clearTokenCache() {
  _adminToken = null
  _teacherToken = null
}
