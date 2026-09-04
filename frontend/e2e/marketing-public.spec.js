import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const publicRoutes = ['/', '/vantagens', '/como-funciona', '/sobre', '/ajuda', '/contacto']
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
})
