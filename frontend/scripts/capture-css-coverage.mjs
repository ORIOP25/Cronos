import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const baseUrl = process.argv[2] || process.env.BASE_URL || 'http://127.0.0.1:5174'
const outputDir = resolve('../documentation/06_frontend_ux/visual-baselines')
const routes = [
  { name: 'marketing', path: '/', ready: '#cronos-hero-title' },
  { name: 'login', path: '/login', ready: '.zen-auth-layout' },
]
const viewports = [
  { width: 1440, height: 900 },
  { width: 768, height: 900 },
  { width: 375, height: 812 },
]

const browser = await chromium.launch({ headless: true })
const results = []

for (const route of routes) {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport })
    await page.coverage.startCSSCoverage({ resetOnNavigation: false, reportAnonymousScripts: true })
    await page.goto(`${baseUrl}${route.path}`)
    await page.locator(route.ready).waitFor()
    const entries = await page.coverage.stopCSSCoverage()
    const totalBytes = entries.reduce((sum, entry) => sum + entry.text.length, 0)
    const usedBytes = entries.reduce((sum, entry) => sum + entry.ranges.reduce((rangeSum, range) => rangeSum + range.end - range.start, 0), 0)
    results.push({
      route: route.name,
      viewport,
      totalBytes,
      usedBytes,
      usedPercent: totalBytes ? Number(((usedBytes / totalBytes) * 100).toFixed(2)) : 0,
      files: entries.map((entry) => ({ url: entry.url, totalBytes: entry.text.length, ranges: entry.ranges })),
    })
    await page.close()
  }
}

await browser.close()
await mkdir(outputDir, { recursive: true })
await writeFile(resolve(outputDir, 'css-coverage.json'), `${JSON.stringify(results, null, 2)}\n`)
for (const result of results) {
  console.log(`${result.route} ${result.viewport.width}px: ${result.usedPercent}% CSS used`)
}
