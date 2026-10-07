import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './fixtures.js'

test('public routes render accessible content and keep canonical aliases', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/public-routing' },
}, async ({ page }) => {
  test.setTimeout(90_000)
  for (const route of ['/', '/vantagens', '/como-funciona', '/sobre', '/ajuda', '/contacto']) {
    const response = await page.goto(route)
    expect(response.status(), route).toBe(200)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Navegação principal' })).toBeVisible()
    expect((await new AxeBuilder({ page }).analyze()).violations, route).toEqual([])
  }
  for (const [alias, canonical] of [['/about', '/sobre'], ['/contact', '/contacto'], ['/privacy', '/privacidade']]) {
    const response = await page.goto(alias)
    expect(response.status(), alias).toBe(200)
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `https://cronos.pt${canonical}`)
  }
})

test('all public legal documents remain readable after reload', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/legal-pages' },
}, async ({ page }) => {
  for (const route of ['/termos', '/privacidade', '/dpa', '/cookies']) {
    const response = await page.goto(route)
    expect(response.status(), route).toBe(200)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const heading = await page.getByRole('heading', { level: 1 }).innerText()
    expect(heading.trim().length).toBeGreaterThan(5)
    expect((await page.getByRole('main').innerText()).length).toBeGreaterThan(500)
    await page.reload()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
  }
})

test('unknown public routes return an actual 404 and offer a working home link', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/public-404' },
}, async ({ page, runtime }) => {
  const pathname = '/acceptance-public-missing-path'
  await runtime.action('public-404', [{ origin: 'https://cronos.pt', pathname, method: 'GET', status: 404, action: 'public-404' }], async () => {
    const response = await page.goto(pathname)
    expect(response.status()).toBe(404)
    await expect(page.getByRole('heading', { name: 'Página não encontrada' })).toBeVisible()
  })
  await page.getByRole('link', { name: 'Voltar ao início', exact: true }).click()
  await expect(page).toHaveURL('https://cronos.pt/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})
