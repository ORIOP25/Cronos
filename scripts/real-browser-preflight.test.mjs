import assert from 'node:assert/strict'
import test from 'node:test'
import { preflight, productionDependencies } from './real-browser-preflight.mjs'

const environment = { BASE_URL: 'https://cronos.pt', E2E_EXPECTED_REVISION: 'a'.repeat(40), E2E_ADMIN_EMAIL: 'admincronos100@gmail.com', E2E_TEACHER_EMAIL: 'professorcronos100@gmail.com' }

test('missing live credentials are dependencies and never start external effects', async () => {
  let effects = 0
  const result = await preflight(environment, { fetchImpl: () => { effects++; throw new Error('network should not start') }, inspect: () => { effects++; throw new Error('inspection should not start') } })
  assert.equal(result.status, 'dependency_unavailable')
  assert.ok(result.missing.includes('E2E_GMAIL_ADMIN_REFRESH_TOKEN'))
  assert.equal(effects, 0)
})

test('preflight requires administrative cleanup identity separately from browser access', () => {
  assert.ok(productionDependencies(environment).includes('E2E_ADMIN_SSH_KEY'))
  assert.ok(productionDependencies(environment).includes('E2E_REGISTRY_HMAC_KEY'))
})

test('historical acceptance requires the persistent teacher credential before browser effects', () => {
  assert.ok(productionDependencies(environment).includes('E2E_HISTORY_TEACHER_PASSWORD'))
  assert.ok(productionDependencies(environment).includes('E2E_HISTORY_ADMIN_PASSWORD'))
})

test('missing production code sender blocks the campaign before any account is created', async () => {
  const configured = { ...environment }
  for (const name of productionDependencies({})) configured[name] = 'configured'
  delete configured.E2E_GMAIL_CODE_SENDER
  const result = await preflight(configured, { fetchImpl: () => { throw new Error('Unexpected external request') } })
  assert.equal(result.status, 'dependency_unavailable')
  assert.deepEqual(result.missing, ['E2E_GMAIL_CODE_SENDER'])
})
