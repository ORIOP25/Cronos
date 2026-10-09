import assert from 'node:assert/strict'
import test from 'node:test'
import { preflight, productionDependencies, publicDiagnosticDependencies, publicPreflight } from './real-browser-preflight.mjs'
import { deploymentConfig } from '../frontend/e2e/utils/deployments.js'

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
  assert.ok(productionDependencies(environment).includes('E2E_SECRET_REGISTRY'))
})

test('preflight never reports ready without the private secret registry', async () => {
  let effects = 0
  const configured = { ...environment }
  for (const name of productionDependencies({})) configured[name] = 'configured'
  configured.E2E_ARTIFACT_KEY = Buffer.alloc(32, 7).toString('base64')
  delete configured.E2E_SECRET_REGISTRY
  const result = await preflight(configured, { fetchImpl: () => { effects++; throw new Error('network should not start') }, inspect: () => { effects++; throw new Error('inspection should not start') } })
  assert.equal(result.status, 'dependency_unavailable')
  assert.deepEqual(result.missing, ['E2E_SECRET_REGISTRY'])
  assert.equal(effects, 0)
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

test('preflight and every acceptance group consume the same deployment provider configuration', () => {
  const configured = { ...environment }
  for (const name of productionDependencies({})) configured[name] = 'configured'
  const built = deploymentConfig(configured)
  assert.deepEqual(built, {
    expectedRevision: configured.E2E_EXPECTED_REVISION,
    cloudflare: { token: 'configured', account: 'configured', project: 'configured' },
    railway: { token: 'configured', tokenType: 'configured', project: 'configured', environment: 'configured', services: { api: 'configured', worker: 'configured', supervisor: 'configured', beat: 'configured' } },
  })
  // Every provider identity the shared configuration reads is a required preflight dependency.
  for (const name of ['CLOUDFLARE_API_TOKEN', 'E2E_CLOUDFLARE_ACCOUNT_ID', 'E2E_CLOUDFLARE_PROJECT', 'E2E_RAILWAY_TOKEN', 'E2E_RAILWAY_TOKEN_TYPE', 'E2E_RAILWAY_PROJECT_ID', 'E2E_RAILWAY_ENVIRONMENT_ID', 'E2E_RAILWAY_API_SERVICE_ID', 'E2E_RAILWAY_WORKER_SERVICE_ID', 'E2E_RAILWAY_SUPERVISOR_SERVICE_ID', 'E2E_RAILWAY_BEAT_SERVICE_ID']) {
    assert.ok(productionDependencies({}).includes(name), name)
  }
})

function publicEnvironment() {
  const configured = { ...environment }
  for (const name of publicDiagnosticDependencies({})) configured[name] = 'configured'
  configured.E2E_ARTIFACT_KEY = Buffer.alloc(32, 7).toString('base64')
  configured.E2E_REGISTRY_HMAC_KEY = Buffer.alloc(32, 8).toString('base64')
  return configured
}

test('public readonly diagnosis never depends on Gmail, history, a persistent school or administrative SSH', () => {
  const dependencies = publicDiagnosticDependencies({})
  for (const forbidden of ['E2E_GMAIL_CLIENT_ID', 'E2E_GMAIL_ADMIN_REFRESH_TOKEN', 'E2E_GMAIL_CODE_SENDER', 'E2E_PERSISTENT_REGISTRY', 'E2E_ADMIN_SSH_KEY', 'E2E_HISTORY_TEACHER_PASSWORD', 'E2E_HISTORY_ADMIN_PASSWORD']) {
    assert.equal(dependencies.includes(forbidden), false, forbidden)
  }
  for (const required of ['CLOUDFLARE_API_TOKEN', 'E2E_RAILWAY_BEAT_SERVICE_ID', 'E2E_ARTIFACT_KEY', 'E2E_REGISTRY_HMAC_KEY', 'E2E_SECRET_REGISTRY']) {
    assert.ok(dependencies.includes(required), required)
  }
  const configured = publicEnvironment()
  delete configured.E2E_GMAIL_ADMIN_REFRESH_TOKEN
  delete configured.E2E_GMAIL_CODE_SENDER
  delete configured.E2E_PERSISTENT_REGISTRY
  delete configured.E2E_ADMIN_SSH_KEY
  delete configured.E2E_HISTORY_TEACHER_PASSWORD
  assert.deepEqual(publicDiagnosticDependencies(configured), [])
})

test('public preflight blocks before any external effect when a provider or protection key is missing', async () => {
  let effects = 0
  const fetchImpl = () => { effects += 1; throw new Error('network should not start') }
  const missingProvider = await publicPreflight({ ...environment }, { fetchImpl })
  assert.equal(missingProvider.status, 'dependency_unavailable')
  assert.ok(missingProvider.missing.includes('CLOUDFLARE_API_TOKEN'))
  const configured = publicEnvironment()
  delete configured.E2E_REGISTRY_HMAC_KEY
  const missingKey = await publicPreflight(configured, { fetchImpl })
  assert.equal(missingKey.status, 'dependency_unavailable')
  assert.deepEqual(missingKey.missing, ['E2E_REGISTRY_HMAC_KEY'])
  assert.equal(effects, 0)
  await assert.rejects(publicPreflight({ ...environment, BASE_URL: 'http://localhost:5173' }, { fetchImpl }), /BASE_URL/)
  assert.equal(effects, 0)
})
