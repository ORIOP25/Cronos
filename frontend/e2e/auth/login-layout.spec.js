import { expect, test } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

test.use({ storageState: { cookies: [], origins: [] } })

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`login sem overflow em ${viewport.width}x${viewport.height} com Clerk real`, async ({ browser }) => {
    const context = await browser.newContext({ viewport, storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()

    try {
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.cl-formFieldInput').first()).toBeVisible({ timeout: 15_000 })
      await expect(page.locator('.zen-auth-page--login')).toBeVisible()

      const dimensions = await page.evaluate(() => ({
        documentHeight: document.documentElement.scrollHeight,
        documentWidth: document.documentElement.scrollWidth,
        viewportHeight: window.innerHeight,
        viewportWidth: window.innerWidth,
      }))

      expect(dimensions.documentHeight).toBeLessThanOrEqual(dimensions.viewportHeight)
      expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
    } finally {
      await context.close()
    }
  })
}

for (const viewport of [
  { width: 375, height: 667 },
  { width: 1280, height: 480 },
]) {
  test(`login mantém scroll natural em ${viewport.width}x${viewport.height}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport, storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()

    try {
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.cl-formFieldInput').first()).toBeVisible({ timeout: 15_000 })

      const dimensions = await page.evaluate(() => ({
        documentHeight: document.documentElement.scrollHeight,
        viewportHeight: window.innerHeight,
        pageOverflowY: getComputedStyle(document.querySelector('.zen-auth-page--login')).overflowY,
      }))

      expect(dimensions.documentHeight).toBeGreaterThan(dimensions.viewportHeight)
      expect(dimensions.pageOverflowY).toBe('visible')
      await page.locator('.zen-auth-form-footer').scrollIntoViewIfNeeded()
      await expect(page.locator('.zen-auth-form-footer')).toBeVisible()
    } finally {
      await context.close()
    }
  })
}
