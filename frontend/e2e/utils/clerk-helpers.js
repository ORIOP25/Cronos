/**
 * Helpers de autenticação Clerk para E2E Playwright.
 *
 * Abordagem: injeta token Clerk real como cookie __session (same-origin).
 * O backend valida o token via clerk_sdk.authenticate_request().
 */

import { getOrCreateAdminToken, getOrCreateTeacherToken } from './clerk-tokens.js'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

/**
 * Autentica como admin com token Clerk real.
 * Injeta o cookie __session antes de navegar.
 */
export async function loginAsAdminReal(page) {
  const token = await getOrCreateAdminToken()
  await page.context().addCookies([{
    name: '__session',
    value: token,
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    secure: false,
    sameSite: 'Lax',
  }])
}

/**
 * Autentica como teacher com token Clerk real.
 */
export async function loginAsTeacherReal(page) {
  const token = await getOrCreateTeacherToken()
  await page.context().addCookies([{
    name: '__session',
    value: token,
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    secure: false,
    sameSite: 'Lax',
  }])
}

/**
 * Navega para uma rota e espera a página carregar completamente.
 */
export async function goTo(page, path) {
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle' })
}

/**
 * Espera que a página contenha o texto indicado (timeout 10s).
 */
export async function expectText(page, text) {
  await page.waitForSelector(`text=${text}`, { timeout: 10000 })
}

/**
 * Espera que a resposta de uma chamada API específica tenha status 200.
 */
export async function expectApiOk(page, urlPattern) {
  const response = await page.waitForResponse(
    (res) => res.url().includes(urlPattern) && res.status() === 200,
    { timeout: 10000 }
  )
  return response
}
