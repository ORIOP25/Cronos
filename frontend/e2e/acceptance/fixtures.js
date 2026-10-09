import { test as base, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { observeAcceptanceActivity, observeAcceptanceRuntime } from '../utils/acceptance-runtime.js'
import { beginProofSession, finishProofSession, noteActorObservation, notePageActivity, notePersistentSchoolObservation, noteSchoolObservation, proofArtifactRoot, publicReadonlySelection } from '../utils/acceptance-proof.js'
import { recordGroupRevisionSnapshot } from '../utils/deployments.js'
import { recordSecretFile, recordUiActorFile, recordUiSchoolFile, signRegistry, verifyRegistry } from '../../../scripts/e2e-run-registry.mjs'
import { cleanupProductionCampaign } from '../../../scripts/cleanup-production-campaign.mjs'
import { createGmailReader, deliveredMessageSecrets } from '../utils/gmail.js'

export const test = base.extend({
  deliveredMail: async ({ baseURL }, runFixture) => {
    if (baseURL !== 'https://cronos.pt') throw new Error('Delivered mail requires production acceptance')
    const readers = new Map()
    await runFixture(async (actor, criteria) => {
      if (!['admin', 'teacher'].includes(actor)) throw new Error('Unknown dedicated mailbox')
      if (!readers.has(actor)) readers.set(actor, await createGmailReader({
        clientId: process.env.E2E_GMAIL_CLIENT_ID,
        clientSecret: process.env.E2E_GMAIL_CLIENT_SECRET,
        refreshToken: process.env[`E2E_GMAIL_${actor.toUpperCase()}_REFRESH_TOKEN`],
        mailbox: process.env[`E2E_${actor.toUpperCase()}_EMAIL`],
      }))
      const message = await readers.get(actor).poll(criteria)
      if (criteria.purpose !== 'contact') {
        for (const secret of deliveredMessageSecrets(message)) await recordSecretFile(process.env.E2E_SECRET_REGISTRY, secret)
      }
      return message
    })
  },
  registerSecret: async ({ baseURL }, runFixture) => {
    if (baseURL !== 'https://cronos.pt') throw new Error('Dynamic credentials require production acceptance')
    await runFixture(value => recordSecretFile(process.env.E2E_SECRET_REGISTRY, value))
  },
  provenance: async ({ page }, runFixture, testInfo) => {
    await runFixture({
      async exportBeforeDeletion(testInfo, selected) {
        if (process.env.E2E_PREPARATION_REPORT) throw new Error('Preparation cannot delete its retained school')
        const key = Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64')
        const registry = verifyRegistry(JSON.parse(await readFile(process.env.E2E_RUN_REGISTRY, 'utf8')), key)
        const school = registry.organizations.find(item => item.local_id === selected.local_id && item.clerk_id === selected.clerk_id)
        if (registry.run_id !== process.env.E2E_RUN_ID || school?.type !== 'disposable' || school.creation_run_id !== registry.run_id) throw new Error('UI deletion requires an owned disposable school from this run')
        const active = await page.evaluate(() => ({ organization: window.Clerk?.organization?.id, actor: window.Clerk?.user?.id }))
        if (active.organization !== school.clerk_id || active.actor !== school.creator_id) throw new Error('UI deletion requires the actual founder and active school')
        const path = testInfo.outputPath('pre-deletion-ui-registry.json')
        await writeFile(path, JSON.stringify(signRegistry({ ...registry, organizations: [school] }, key)), { flag: 'wx', mode: 0o600 })
        const result = await cleanupProductionCampaign({ registryPath: path, runId: registry.run_id,
          expectedRevision: process.env.E2E_EXPECTED_REVISION, artifactRoot: process.env.PLAYWRIGHT_OUTPUT_DIR }, process.env, { exportOnly: true })
        expect(result.status, 'Authenticated administrative export must precede native UI deletion').toBe('exported')
        expect(result.exported).toEqual([school.local_id])
        await testInfo.attach('pre-ui-deletion-protected-backup', {
          path: join(process.env.PLAYWRIGHT_OUTPUT_DIR, `organization-${school.local_id}.zip.enc`), contentType: 'application/octet-stream',
        })
        return result
      },
      async recordCurrentActor(observedPage = page) {
        if (!process.env.E2E_RUN_REGISTRY) return
        const actor = await observedPage.evaluate(() => {
          const user = window.Clerk?.user
          if (!user) return null
          return { id: user.id, email: user.primaryEmailAddress?.emailAddress, created_at: user.createdAt?.toISOString() ?? null }
        })
        if (!actor || !['admincronos100', 'professorcronos100'].some(base => actor.email === `${base}+${process.env.E2E_RUN_ID}@gmail.com`)) return
        await recordUiActorFile(process.env.E2E_RUN_REGISTRY, Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'), process.env.E2E_RUN_ID, actor, new Date().toISOString())
        noteActorObservation(testInfo)
      },
      // Call after creating the school through visible controls, using its founder's page.
      async recordCreatedSchool(type, observedPage = page) {
        await this.recordCurrentActor(observedPage)
        const school = await observedPage.evaluate(async () => {
          const clerk = window.Clerk
          const organization = clerk?.organization
          if (!organization || !clerk.user || !clerk.session) throw new Error('UI school identity is not active')
          const response = await fetch('/api/v1/members/me', { redirect: 'error', headers: { Authorization: `Bearer ${await clerk.session.getToken()}` } })
          if (!response.ok) throw new Error('Local school identity is unavailable')
          const member = await response.json()
          const memberships = await organization.getMemberships({ pageSize: 100, initialPage: 1 })
          // A campaign creates two Clerk actors; never accept a partial inventory.
          if (memberships.total_count !== memberships.data.length) throw new Error('UI school member inventory is incomplete')
          return {
            local_id: member.organization_id, clerk_id: organization.id, creator_id: clerk.user.id,
            created_at: organization.createdAt.toISOString(),
            actors: memberships.data.map(item => ({ id: item.publicUserData.userId, email: item.publicUserData.identifier })),
          }
        })
        await recordUiSchoolFile(process.env.E2E_RUN_REGISTRY, Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'), process.env.E2E_RUN_ID, school, type, new Date().toISOString())
        noteSchoolObservation(testInfo)
      },
      // Observe an already signed persistent school through the live UI session.
      // It grants provenance only and never writes the actor as a fresh record.
      async observePersistentSchool(school, observedPage = page) {
        const observed = await observedPage.evaluate(() => ({
          actor_id: window.Clerk?.user?.id ?? null,
          organization_id: window.Clerk?.organization?.id ?? null,
        }))
        if (!notePersistentSchoolObservation(testInfo, school, observed)) {
          throw new Error('Persistent school observation does not match the signed actor and active organization')
        }
      },
    })
  },
  runtime: [async ({ page, provenance }, runFixture, testInfo) => {
    if (process.env.BASE_URL !== 'https://cronos.pt') throw new Error('Acceptance requires exactly https://cronos.pt')
    // W10.1: under the readonly public diagnosis, refuse an extra, unannotated,
    // identity or contact group before its body can send mail or write state.
    const selection = publicReadonlySelection({ mode: process.env.CAMPAIGN_MODE, annotations: testInfo.annotations })
    if (!selection.ok) throw new Error(selection.reason)
    // Evidence paths are relative to the reporter's artifact root (the configured project output dir).
    beginProofSession(testInfo, proofArtifactRoot(testInfo))
    observeAcceptanceActivity(() => notePageActivity(testInfo))
    const runtime = observeAcceptanceRuntime(page)
    try {
      // W04.6: a publication during the campaign invalidates the previous
      // revision. Verify the live production revision and materialize its proof
      // before this group body starts.
      await recordGroupRevisionSnapshot(testInfo, process.env)
      await runFixture(runtime)
      await page.waitForLoadState('load')
      await provenance.recordCurrentActor()
      const screenshot = testInfo.outputPath('browser-evidence.png')
      await page.screenshot({ path: screenshot, fullPage: true, mask: [page.locator('input, textarea')] })
      await testInfo.attach('browser-evidence', { path: screenshot, contentType: 'image/png' })
      expect(runtime.errors, 'Unanticipated browser runtime failures').toEqual([])
    } finally {
      observeAcceptanceActivity(null)
      runtime.dispose()
      finishProofSession(testInfo)
    }
  }, { auto: true }],
})

export { expect }
