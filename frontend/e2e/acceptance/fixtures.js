import { test as base, expect } from '@playwright/test'
import { observeAcceptanceRuntime } from '../utils/acceptance-runtime.js'
import { recordUiActorFile } from '../../../scripts/e2e-run-registry.mjs'

export const test = base.extend({
  provenance: async ({ page }, runFixture) => {
    await runFixture({
      async recordCurrentActor() {
        if (!process.env.E2E_RUN_REGISTRY) return
        const actor = await page.evaluate(() => {
          const user = window.Clerk?.user
          if (!user) return null
          return { id: user.id, email: user.primaryEmailAddress?.emailAddress, created_at: user.createdAt?.toISOString() ?? null }
        })
        if (!actor || !['admincronos100', 'professorcronos100'].some(base => actor.email === `${base}+${process.env.E2E_RUN_ID}@gmail.com`)) return
        await recordUiActorFile(process.env.E2E_RUN_REGISTRY, Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'), process.env.E2E_RUN_ID, actor, new Date().toISOString())
      },
    })
  },
  runtime: [async ({ page, provenance }, runFixture, testInfo) => {
    if (process.env.BASE_URL !== 'https://cronos.pt') throw new Error('Acceptance requires exactly https://cronos.pt')
    const runtime = observeAcceptanceRuntime(page)
    try {
      await runFixture(runtime)
      await page.waitForLoadState('load')
      await provenance.recordCurrentActor()
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
