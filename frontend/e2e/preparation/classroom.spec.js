import { readFile, writeFile } from 'node:fs/promises'
import { relative, sep } from 'node:path'
import { verifyRegistry } from '../../../scripts/e2e-run-registry.mjs'
import { protectEvidence } from '../../../scripts/protect-test-evidence.mjs'
import { runIdentityCampaign } from '../utils/ui-identity-campaign.js'
import { readSchoolResource } from '../utils/ui-school.js'
import { test, expect } from '../acceptance/fixtures.js'

test('prepare a persistent full school through native UI for future historical campaigns', async ({ page, browser, provenance, deliveredMail, registerSecret }, testInfo) => {
  if (!process.env.E2E_PREPARATION_REPORT) throw new Error('Persistent preparation requires its separate result path')
  let credentialsPath
  await runIdentityCampaign({ page, browser, provenance, deliveredMail, registerSecret }, testInfo, {
    persistent: true,
    async persistCredentials(credentials) {
      const path = testInfo.outputPath('persistent-credentials.json.enc')
      credentialsPath = relative(process.env.PLAYWRIGHT_OUTPUT_DIR, path).split(sep).join('/')
      await writeFile(path, protectEvidence(Buffer.from(JSON.stringify(credentials)), Buffer.from(process.env.E2E_ARTIFACT_KEY, 'base64'),
        { run_id: process.env.E2E_RUN_ID, path: credentialsPath.slice(0, -4) }), { flag: 'wx', mode: 0o600 })
      // Reference, not a copy: a Playwright copy would carry a different authenticated path.
      await testInfo.attach('protected-persistent-login-recovery', { body: Buffer.from(JSON.stringify({ protected_path: credentialsPath })), contentType: 'application/json' })
    },
    async onPrepared({ page, original, converted, generated, schoolPeriod }) {
      const registry = verifyRegistry(JSON.parse(await readFile(process.env.E2E_RUN_REGISTRY, 'utf8')),
        Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY, 'base64'))
      expect(registry.run_id).toBe(process.env.E2E_RUN_ID)
      expect(registry.organizations).toHaveLength(1)
      const organization = registry.organizations[0]
      expect(organization.type).toBe('persistent')
      expect(organization.provenance).toBe('ui')
      expect(organization.actors).toHaveLength(2)
      const publication = await readSchoolResource(page, 'scheduler/status')
      expect(publication).toMatchObject({ publication_state: 'PUBLISHED', active_version_id: generated.versionId,
        active_job: null, pending_proposal: null })
      const result = { schema_version: 1, status: 'prepared', run_id: registry.run_id,
        prepared_at: new Date().toISOString(), revision: process.env.E2E_EXPECTED_REVISION, organization,
        original_files: original.files, counts: original.counts, required_minutes: original.required_minutes,
        publication, proposal_id: generated.proposal.proposal_id, school_period: schoolPeriod, teacher_id: converted.member.teacher_id,
        credentials_path: credentialsPath, history_verified: false }
      await writeFile(process.env.E2E_PREPARATION_REPORT, JSON.stringify(result), { flag: 'wx', mode: 0o600 })
      await testInfo.attach('persistent-school-preparation', { body: Buffer.from(JSON.stringify(result)), contentType: 'application/json' })
    },
  })
})
