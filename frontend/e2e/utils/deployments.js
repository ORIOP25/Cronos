import { writeFile } from 'node:fs/promises'
import { COMPONENTS } from './acceptance-policy.js'

// Verified against Railway's live schema on 2026-10-07.
const RAILWAY_QUERY = `query E2EDeployments($serviceId: String!, $environmentId: String!, $input: DeploymentListInput!, $after: String) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    latestDeployment { id status deploymentStopped meta }
  }
  deployments(first: 100, input: $input, after: $after) {
    edges { node { id status deploymentStopped meta } }
    pageInfo { hasNextPage endCursor }
  }
}`

// One provider configuration is shared by the standalone preflight and by the
// per-group acceptance check, so the provider identities cannot drift.
export function deploymentConfig(environment, expectedRevision = environment.E2E_EXPECTED_REVISION) {
  return {
    expectedRevision,
    cloudflare: { token: environment.CLOUDFLARE_API_TOKEN, account: environment.E2E_CLOUDFLARE_ACCOUNT_ID, project: environment.E2E_CLOUDFLARE_PROJECT },
    railway: {
      token: environment.E2E_RAILWAY_TOKEN,
      tokenType: environment.E2E_RAILWAY_TOKEN_TYPE,
      project: environment.E2E_RAILWAY_PROJECT_ID,
      environment: environment.E2E_RAILWAY_ENVIRONMENT_ID,
      services: Object.fromEntries(['api', 'worker', 'supervisor', 'beat'].map(name => [name, environment[`E2E_RAILWAY_${name.toUpperCase()}_SERVICE_ID`]])),
    },
  }
}

async function json(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(20_000), cache: 'no-store' })
  if (!response.ok) throw new Error(`Deployment dependency unavailable: HTTP ${response.status}`)
  try { return await response.json() } catch { throw new Error('Deployment dependency returned invalid JSON') }
}

async function railwayDeployment(railway, name, expectedRevision, fetchImpl) {
  const seenCursors = new Set()
  const seenIds = new Set()
  const active = []
  let after = null
  let latest
  do {
    const result = await json(fetchImpl, 'https://backboard.railway.com/graphql/v2', {
      method: 'POST', headers: { 'Content-Type': 'application/json', [railway.tokenType === 'project' ? 'Project-Access-Token' : 'Authorization']: railway.tokenType === 'project' ? railway.token : `Bearer ${railway.token}` },
      body: JSON.stringify({ query: RAILWAY_QUERY, variables: { serviceId: railway.services[name], environmentId: railway.environment, after, input: { projectId: railway.project, environmentId: railway.environment, serviceId: railway.services[name] } } }),
    })
    const connection = result.data?.deployments
    const current = result.data?.serviceInstance?.latestDeployment
    if (result.errors?.length || !current?.id || !Array.isArray(connection?.edges) || typeof connection.pageInfo?.hasNextPage !== 'boolean') throw new Error(`Railway deployment response incomplete: ${name}`)
    if (current.status !== 'SUCCESS' || current.deploymentStopped !== false || current.meta?.commitHash !== expectedRevision || (latest && latest.id !== current.id)) throw new Error(`Railway deployment changed or does not match: ${name}`)
    latest = current
    for (const { node } of connection.edges) {
      if (!node?.id || seenIds.has(node.id) || typeof node.deploymentStopped !== 'boolean') throw new Error(`Railway deployment history incomplete: ${name}`)
      seenIds.add(node.id)
      if (!node.deploymentStopped) active.push(node)
    }
    if (!connection.pageInfo.hasNextPage) break
    after = connection.pageInfo.endCursor
    if (typeof after !== 'string' || !after || seenCursors.has(after) || seenCursors.size >= 100) throw new Error(`Railway deployment pagination incomplete: ${name}`)
    seenCursors.add(after)
  } while (after !== null)
  if (active.length !== 1 || active[0].id !== latest.id || active[0].status !== 'SUCCESS' || active[0].meta?.commitHash !== expectedRevision) throw new Error(`Railway active deployment does not match: ${name}`)
  return latest
}

export function assertRevisionSnapshot(snapshot, expectedRevision) {
  if (!/^[a-f0-9]{40}$/.test(expectedRevision || '')) throw new Error('Expected full deployment revision required')
  for (const component of COMPONENTS) {
    if (snapshot.components?.[component] !== expectedRevision) throw new Error(`Deployment revision mismatch: ${component}`)
  }
}

export async function readDeploymentSnapshot(config, { fetchImpl = fetch } = {}) {
  const { cloudflare, railway, expectedRevision } = config
  if (!cloudflare?.token || !cloudflare.account || !cloudflare.project || !railway?.token || !railway.project || !railway.environment || !['account', 'project'].includes(railway.tokenType)) throw new Error('Explicit deployment provider configuration required')
  for (const component of COMPONENTS.filter(name => name !== 'frontend')) {
    if (!railway.services?.[component]) throw new Error(`Missing Railway service: ${component}`)
  }
  const frontend = await json(fetchImpl, `https://cronos.pt/revision.json?expected=${expectedRevision}`, { headers: { 'Cache-Control': 'no-cache' } })
  if (frontend.schema_version !== 1 || frontend.verifiable !== true || frontend.source !== 'cloudflare-pages') throw new Error('Frontend build revision is not verifiable')
  const pages = await json(fetchImpl, `https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(cloudflare.account)}/pages/projects/${encodeURIComponent(cloudflare.project)}/deployments?env=production`, { headers: { Authorization: `Bearer ${cloudflare.token}` } })
  if (pages.success !== true || !Array.isArray(pages.result) || !pages.result.length) throw new Error('Pages production deployment unavailable')
  // API order is newest first. An older successful deployment cannot mask a newer failure.
  const deployed = pages.result[0]
  if (deployed.environment !== 'production' || deployed.project_name !== cloudflare.project || deployed.latest_stage?.name !== 'deploy' || deployed.latest_stage.status !== 'success' || deployed.deployment_trigger?.metadata?.commit_hash !== expectedRevision) throw new Error('Pages production deployment does not match the campaign')
  const ready = await json(fetchImpl, 'https://api.cronos.pt/health/ready')
  if (ready.status !== 'ok' || ready.revision !== expectedRevision || ready.postgres !== 'connected' || ready.redis !== 'connected') throw new Error('Production API readiness does not match the campaign')
  const components = { frontend: frontend.revision }
  const deployments = { frontend: deployed.id }
  for (const name of COMPONENTS.filter(item => item !== 'frontend')) {
    const latest = await railwayDeployment(railway, name, expectedRevision, fetchImpl)
    components[name] = latest.meta?.commitHash
    deployments[name] = latest.id
  }
  const snapshot = { checked_at: new Date().toISOString(), components, deployments }
  assertRevisionSnapshot(snapshot, expectedRevision)
  return snapshot
}

// W04.6: a publication during the campaign invalidates the previous revision.
// Verify the live production revision before a group starts, using the expected
// SHA from the environment only, and materialize its proof. A provider mismatch
// throws before any snapshot is attached, so the group body never runs.
export async function recordGroupRevisionSnapshot(testInfo, environment, { fetchImpl = fetch } = {}) {
  const snapshot = await readDeploymentSnapshot(deploymentConfig(environment), { fetchImpl })
  assertRevisionSnapshot(snapshot, environment.E2E_EXPECTED_REVISION)
  const path = testInfo.outputPath('group-revision-snapshot.json')
  await writeFile(path, `${JSON.stringify(snapshot, null, 2)}\n`, { flag: 'wx', mode: 0o600 })
  await testInfo.attach('group-revision-snapshot', { path, contentType: 'application/json' })
  return snapshot
}
