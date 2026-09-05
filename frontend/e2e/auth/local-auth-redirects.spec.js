import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  goTo,
} from '../utils/clerk-helpers.js'
import { E2E_BASE_URL } from '../utils/e2e-config.js'

test.use({ storageState: { cookies: [], origins: [] } })

const APP_ORIGIN = new URL(E2E_BASE_URL).origin

async function expectLocalPathLink(page, path) {
  const link = page.locator(`a[href$="${path}"]`).first()
  await expect(link).toBeVisible()
  const href = await link.getAttribute('href')
  const linkUrl = new URL(href, page.url())
  expect(linkUrl.origin).toBe(APP_ORIGIN)
  expect(linkUrl.pathname).toBe(path)
}

function redirectUrlFromLogin(loginUrl) {
  const hashUrl = loginUrl.hash
    ? new URL(loginUrl.hash.slice(1), APP_ORIGIN)
    : null
  return loginUrl.searchParams.get('redirect_url') || hashUrl?.searchParams.get('redirect_url')
}

test.describe('redirecionamentos de autenticação locais', () => {
  for (const path of ['/dashboard', '/my-availability', '/create-org']) {
    test(`encaminha ${path} para login na mesma origem`, async ({ browser }) => {
      const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
      const page = await context.newPage()

      try {
        await goTo(page, path)
        await expect(page).toHaveURL(/\/login(?:[?#].*)?$/, { timeout: 15_000 })

        const loginUrl = new URL(page.url())
        expect(loginUrl.origin).toBe(APP_ORIGIN)
        expect(loginUrl.pathname).toBe('/login')
        expect(redirectUrlFromLogin(loginUrl)).toBeTruthy()
      } finally {
        await context.close()
      }
    })
  }

  test('preserva caminho, query e fragmento em redirect_url', async ({ browser }) => {
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()

    try {
      const target = '/dashboard?view=week&mode=teacher#availability'
      await goTo(page, target)
      await expect(page).toHaveURL(/\/login(?:[?#].*)?$/, { timeout: 15_000 })

      const loginUrl = new URL(page.url())
      const redirectTarget = new URL(redirectUrlFromLogin(loginUrl), APP_ORIGIN)
      expect(loginUrl.origin).toBe(APP_ORIGIN)
      expect(loginUrl.pathname).toBe('/login')
      expect(redirectTarget.pathname).toBe('/dashboard')
      expect(redirectTarget.search).toBe('?view=week&mode=teacher')
      expect(redirectTarget.hash).toBe('#availability')
    } finally {
      await context.close()
    }
  })

  test('mantém locais os links entre login, registo e recuperação', async ({ page }) => {
    attachRuntimeGuards(page)

    await goTo(page, '/login')
    await expectLocalPathLink(page, '/register')
    await expect(page.getByRole('link', { name: /recuperar palavra-passe/i })).toHaveAttribute(
      'href',
      '/recuperar-palavra-passe',
    )

    await goTo(page, '/register')
    await expectLocalPathLink(page, '/login')

    await goTo(page, '/recuperar-palavra-passe')
    await expectLocalPathLink(page, '/login')
  })
})
