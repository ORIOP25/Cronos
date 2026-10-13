import { resolve } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

const SITE = 'https://cronos.pt'
const API = 'https://api.cronos.pt'
const PUBLIC_PAGES = ['/', '/login']
const FULL_SHA = /^[0-9a-f]{40}$/

async function readJson(fetchImpl, url) {
  const response = await fetchImpl(url, { headers: { 'cache-control': 'no-cache' } })
  if (!response.ok) throw new Error(`answered ${response.status}`)
  return response.json()
}

async function observe(failures, label, check) {
  try {
    const failure = await check()
    if (failure) failures.push(failure)
  } catch (error) {
    failures.push(`${label} unreachable: ${error.message}`)
  }
}

// One read-only look at production: no credentials, accounts or business writes.
export async function observeDeployment(expected, { fetchImpl = fetch, backendChanged = true } = {}) {
  const failures = []
  await observe(failures, 'Frontend', async () => {
    const { revision } = await readJson(fetchImpl, `${SITE}/revision.json?expected=${expected}`)
    return revision === expected ? null : `Frontend serves ${revision}`
  })
  await observe(failures, 'API', async () => {
    const health = await readJson(fetchImpl, `${API}/health/ready`)
    if (health.status !== 'ok' || health.postgres !== 'connected' || health.redis !== 'connected') {
      return `API health is ${health.status} (postgres ${health.postgres}, redis ${health.redis})`
    }
    // Railway only redeploys the API for commits that change the backend.
    return backendChanged && health.revision !== expected ? `API serves ${health.revision}` : null
  })
  for (const path of PUBLIC_PAGES) {
    await observe(failures, path, async () => {
      const response = await fetchImpl(`${SITE}${path}`)
      if (!response.ok) return `${path} answered ${response.status}`
      const page = await response.text()
      return page.includes('<div id="root"') && page.includes('<title>Cronos') ? null : `${path} does not render the application shell`
    })
  }
  return { ready: failures.length === 0, failures }
}

// Deploys start on the same push as CI, so wait for them before judging.
async function main() {
  const expected = process.env.EXPECTED_REVISION
  if (!FULL_SHA.test(expected || '')) throw new Error('EXPECTED_REVISION must be a full commit SHA')
  const backendChanged = process.env.BACKEND_CHANGED !== 'false'
  const deadline = Date.now() + Number(process.env.DEPLOY_TIMEOUT_SECONDS || 1200) * 1000
  for (;;) {
    const { ready, failures } = await observeDeployment(expected, { backendChanged })
    if (ready) {
      console.log(`Production serves ${expected} and is healthy.`)
      return 0
    }
    if (Date.now() > deadline) {
      for (const failure of failures) console.error(`::error::${failure}`)
      return 1
    }
    console.log(`Waiting for production: ${failures.join('; ')}`)
    await sleep(20_000)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { process.exitCode = code }, (error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
