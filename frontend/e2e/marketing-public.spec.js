import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { PUBLIC_ASSET_REVISION } from '../src/utils/publicAsset.js'

const publicRoutes = ['/', '/vantagens', '/como-funciona', '/sobre', '/ajuda', '/contacto']
const trustRoutes = ['/sobre', '/about', '/contacto', '/contact', '/privacidade', '/privacy']
const publicViewports = [
  { width: 375, height: 812, name: 'mobile' },
  { width: 768, height: 1024, name: 'tablet' },
  { width: 1280, height: 900, name: 'desktop' },
  { width: 1440, height: 900, name: 'wide' },
]

function relativeLuminance([red, green, blue]) {
  return [red, green, blue]
    .map((channel) => channel / 255)
    .map((channel) => (channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4))
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
}

function parseRgb(value) {
  return value.match(/\d+/g).slice(0, 3).map(Number)
}

test.describe('public marketing site', () => {
  test.setTimeout(60_000)
  for (const route of publicRoutes) {
    test(`${route} passes the accessibility audit`, async ({ page }) => {
      await page.goto(route)
      await expect(page.locator('h1')).toHaveCount(1, { timeout: 30000 })
      const results = await new AxeBuilder({ page }).analyze()
      expect(results.violations).toEqual([])
    })
  }

  for (const viewport of publicViewports) {
    for (const route of publicRoutes) {
      test(`${route} fits ${viewport.name} viewport with accessible CTA`, async ({ page }) => {
        await page.setViewportSize(viewport)
        await page.goto(route)
        await expect(page.locator('h1')).toHaveCount(1, { timeout: 30000 })

        const layout = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          headings: [...document.querySelectorAll('h1, h2, h3')].map((heading) => ({ level: heading.tagName, text: heading.textContent.trim() })),
        }))
        expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1)
        expect(layout.headings.every((heading) => !/\.$/.test(heading.text))).toBe(true)
        if (route === '/vantagens') {
          expect(layout.headings[0].level).toBe('H1')
          expect(layout.headings[1]).toEqual({ level: 'H2', text: 'Comparação entre a gestão manual e o Cronos' })
        }

        const cta = page.locator('.cronos-button').first()
        const contrast = await cta.evaluate((element) => {
          const styles = getComputedStyle(element)
          return { background: styles.backgroundColor, foreground: styles.color }
        })
        const background = relativeLuminance(parseRgb(contrast.background))
        const foreground = relativeLuminance(parseRgb(contrast.foreground))
        const ratio = (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05)
        expect(ratio).toBeGreaterThanOrEqual(4.5)
      })
    }
  }

  test('mobile navigation closes after route selection', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    const toggle = page.getByRole('button', { name: 'Abrir menu de navegação' })
    await toggle.click()
    await expect(page.locator('.cronos-mobile-toggle')).toHaveAttribute('aria-expanded', 'true')
    await page.getByRole('navigation', { name: 'Navegação principal' }).getByRole('link', { name: 'Vantagens' }).click()
    await expect(page).toHaveURL(/\/vantagens$/)
    await expect(page.getByRole('button', { name: 'Abrir menu de navegação' })).toHaveAttribute('aria-expanded', 'false')
  })

  test('contact questionnaire starts with the five-step promise', async ({ page }) => {
    await page.goto('/contacto')
    await expect(page.getByText('5 passos, cerca de 1 minuto')).toBeVisible()
    await page.getByRole('button', { name: 'Começar' }).click()
    await expect(page.getByText('Qual é o principal desafio da sua escola?')).toBeVisible()
  })

  test('serves meaningful trust content when JavaScript is disabled', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false })
    try {
      const noScriptPage = await context.newPage()
      for (const route of trustRoutes) {
        const response = await noScriptPage.goto(route)
        expect(response?.status()).toBe(200)
        await expect(noScriptPage.locator('h1')).toHaveCount(1)
        expect(await noScriptPage.locator('link[rel="stylesheet"][href*="/assets/"]').count()).toBeGreaterThan(0)
        expect(await noScriptPage.locator('img').evaluateAll((images) => images.every((image) => image.complete && image.naturalWidth > 0))).toBe(true)
        expect((await noScriptPage.locator('body').innerText()).replace(/\s+/g, ' ').trim().length).toBeGreaterThan(500)
      }
    } finally {
      await context.close()
    }
  })

  test('serves versioned public assets with their expected MIME types', async ({ request }) => {
    const htmlResponse = await request.get('/')
    expect(htmlResponse.status()).toBe(200)
    const html = await htmlResponse.text()
    const stylesheetHref = html.match(/<link rel="stylesheet" href="(\/assets\/[^" ]+\.css)" \/>/)?.[1]
    const scriptSrc = html.match(/<script type="module" crossorigin src="(\/assets\/[^" ]+\.js)"><\/script>/)?.[1]
    expect(stylesheetHref).toBeTruthy()
    expect(scriptSrc).toBeTruthy()

    const checks = [
      [`/logo.png?v=${PUBLIC_ASSET_REVISION}`, /^image\/png/],
      [`/favicon.ico?v=${PUBLIC_ASSET_REVISION}`, /^image\/(?:x-icon|vnd\.microsoft\.icon)/],
      [`/favicon.png?v=${PUBLIC_ASSET_REVISION}`, /^image\/png/],
      [`/marketing/product/hero-schedule.webp?v=${PUBLIC_ASSET_REVISION}`, /^image\/webp/],
      [stylesheetHref, /^text\/css/],
      [scriptSrc, /^(?:text|application)\/javascript/],
    ]
    for (const [path, contentType] of checks) {
      const response = await request.get(path)
      expect(response.status(), path).toBe(200)
      expect(response.headers()['content-type'], path).toMatch(contentType)
    }
  })

  test('serves the homepage and application shell from distinct initial responses', async ({ request }) => {
    const homepage = await request.get('/')
    expect(homepage.status()).toBe(200)
    expect(await homepage.text()).toContain('cronos-hero')

    for (const path of ['/foundation', '/login', '/register', '/login/tasks/choose-organization']) {
      const response = await request.get(path)
      expect(response.status(), path).toBe(200)
      expect(await response.text(), path).not.toContain('cronos-hero')
    }
  })

  test('keeps alias canonicals and returns a real browser 404', async ({ page }) => {
    for (const [alias, canonical] of [['/about', '/sobre'], ['/contact', '/contacto'], ['/privacy', '/privacidade']]) {
      const response = await page.goto(alias)
      expect(response?.status()).toBe(200)
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `https://cronos.pt${canonical}`)
    }
    const response = await page.goto('/agentic-audit-missing-path')
    expect(response?.status()).toBe(404)
    await expect(page.getByRole('heading', { name: 'Página não encontrada' })).toBeVisible()
  })
})
