import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateProductionConfig } from '../frontend/e2e/utils/acceptance-policy.js'
import { createGmailReader } from '../frontend/e2e/utils/gmail.js'
import { deploymentConfig, readDeploymentSnapshot } from '../frontend/e2e/utils/deployments.js'
import { verifyRegistry } from './e2e-run-registry.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

export function productionDependencies(environment, { preparation = false } = {}) {
  const names = [
    'E2E_GMAIL_CLIENT_ID', 'E2E_GMAIL_CLIENT_SECRET', 'E2E_GMAIL_ADMIN_REFRESH_TOKEN', 'E2E_GMAIL_TEACHER_REFRESH_TOKEN', 'E2E_GMAIL_CODE_SENDER',
    'CLOUDFLARE_API_TOKEN', 'E2E_CLOUDFLARE_ACCOUNT_ID', 'E2E_CLOUDFLARE_PROJECT',
    'E2E_RAILWAY_TOKEN', 'E2E_RAILWAY_TOKEN_TYPE', 'E2E_RAILWAY_PROJECT_ID', 'E2E_RAILWAY_ENVIRONMENT_ID',
    'E2E_RAILWAY_API_SERVICE_ID', 'E2E_RAILWAY_WORKER_SERVICE_ID', 'E2E_RAILWAY_SUPERVISOR_SERVICE_ID', 'E2E_RAILWAY_BEAT_SERVICE_ID',
    'E2E_ARTIFACT_KEY', 'E2E_SECRET_REGISTRY', 'E2E_PERSISTENT_REGISTRY', 'E2E_ADMIN_SSH_KEY', 'E2E_REGISTRY_HMAC_KEY', 'E2E_HISTORY_TEACHER_PASSWORD', 'E2E_HISTORY_ADMIN_PASSWORD',
  ]
  return names.filter(name => !(preparation && ['E2E_HISTORY_TEACHER_PASSWORD', 'E2E_HISTORY_ADMIN_PASSWORD'].includes(name)) && !environment[name])
}

function inspectData(python, directory) {
  return new Promise((accept, reject) => {
    const child = spawn(python, [resolve(ROOT, 'scripts/inspect-e2e-data.py'), directory], { shell: false, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    let output = ''
    child.stdout.on('data', data => { output += data })
    child.stderr.resume()
    child.once('error', reject)
    child.once('exit', code => {
      if (code !== 0) return reject(new Error('Independent original data inspection failed'))
      try { accept(JSON.parse(output)) } catch { reject(new Error('Invalid independent data inspection result')) }
    })
  })
}

export async function preflight(environment, { fetchImpl = fetch, inspect = inspectData, phase = 'before', preparation = false } = {}) {
  const config = validateProductionConfig(environment)
  const missing = productionDependencies(environment, { preparation })
  if (missing.length) return { status: 'dependency_unavailable', phase, missing, checked_at: new Date().toISOString() }
  if (Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64').length !== 32) throw new Error('Evidence key must contain exactly 32 random bytes')
  const envelope = JSON.parse(await readFile(resolve(environment.E2E_PERSISTENT_REGISTRY), 'utf8'))
  const registry = verifyRegistry(envelope, Buffer.from(environment.E2E_REGISTRY_HMAC_KEY, 'base64'))
  if (registry.schema_version !== 1 || !Array.isArray(registry.organizations)) throw new Error('Persistent school registry is invalid')
  const data = await inspect(environment.E2E_PYTHON || 'python', resolve(ROOT, 'frontend/e2e/data/originals'))
  const gmail = {}
  for (const actor of ['admin', 'teacher']) {
    const reader = await createGmailReader({ clientId: environment.E2E_GMAIL_CLIENT_ID, clientSecret: environment.E2E_GMAIL_CLIENT_SECRET, refreshToken: environment[`E2E_GMAIL_${actor.toUpperCase()}_REFRESH_TOKEN`], mailbox: config.mailboxes[actor] }, { fetchImpl })
    gmail[actor] = { mailbox: reader.mailbox, readonly: true, verified: true }
  }
  const snapshot = await readDeploymentSnapshot(deploymentConfig(environment, config.expectedRevision), { fetchImpl })
  return { status: 'ready', phase, checked_at: snapshot.checked_at, components: snapshot.components, deployments: snapshot.deployments, gmail, data: { files: data.files, counts: data.counts, required_minutes: data.required_minutes } }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const output = resolve(ROOT, '.test-artifacts/production-preflight.json')
  let result
  try { result = await preflight(process.env) } catch (error) { result = { status: 'failed', reason: error.message, checked_at: new Date().toISOString() } }
  await mkdir(dirname(output), { recursive: true })
  await writeFile(output, `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify({ status: result.status === 'ready' ? 'ready' : result.status === 'dependency_unavailable' ? 'dependency_unavailable' : 'failed', report: '.test-artifacts/production-preflight.json' }))
  if (result.status !== 'ready') process.exitCode = 1
}
