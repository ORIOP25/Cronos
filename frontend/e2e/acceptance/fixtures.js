import { test as base, expect } from '@playwright/test'
import { observeAcceptanceRuntime } from '../utils/acceptance-runtime.js'

export const test = base.extend({
  runtime: [async ({ page }, runFixture, testInfo) => {
    if (process.env.BASE_URL !== 'https://cronos.pt') throw new Error('Acceptance requires exactly https://cronos.pt')
    const runtime = observeAcceptanceRuntime(page)
    try {
      await runFixture(runtime)
      await page.waitForLoadState('load')
      const identifiers = testInfo.annotations.filter(item => item.type === 'acceptance-case').map(item => item.description)
      const screenshot = testInfo.outputPath('browser-evidence.png')
      await page.screenshot({ path: screenshot, fullPage: true, mask: [page.locator('input, textarea')] })
      await testInfo.attach('browser-evidence', { path: screenshot, contentType: 'image/png' })
      const eligible = testInfo.status === 'passed' && runtime.errors.length === 0
      for (const caseId of identifiers) {
        await testInfo.attach('acceptance-proof', {
          body: Buffer.from(JSON.stringify({ case_id: caseId, eligible, ui_provenance: true })),
          contentType: 'application/json',
        })
      }
      expect(runtime.errors, 'Unanticipated browser runtime failures').toEqual([])
    } finally { runtime.dispose() }
  }, { auto: true }],
})

export { expect }
