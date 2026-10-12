import { spawn } from 'node:child_process'
import { access, lstat, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { delimiter, dirname, join, resolve } from 'node:path'
import { unresolvedUiCreationIntents, verifyRegistry } from './e2e-run-registry.mjs'
import { recoverEvidence } from './protect-test-evidence.mjs'

// Static code only: credentials and the signed registry travel through SSH stdin.
const remoteCode = `import asyncio, base64, contextlib, io, json, os, pathlib, re, sys, tempfile
packet = json.load(sys.stdin)
result = {"run_id": packet["run_id"], "status": "failed"}
exports = []
directory = None
try:
    if packet.get("mode") not in ("cleanup", "export"):
        raise ValueError("Invalid administrative mode")
    if not re.fullmatch(r"[a-z0-9-]+", packet["run_id"]):
        raise ValueError("Invalid run identity")
    if os.environ.get("RAILWAY_GIT_COMMIT_SHA") != packet["expected_revision"]:
        raise ValueError("Administrative revision mismatch")
    if not os.environ.get("CLERK_SECRET_KEY", "").startswith("sk_live_"):
        raise ValueError("Production provider credential required")
    os.environ["E2E_CLEANUP_CLERK_SECRET_KEY"] = os.environ["CLERK_SECRET_KEY"]
    os.environ["E2E_REGISTRY_HMAC_KEY"] = packet["signing_key"]
    os.environ["E2E_ARTIFACT_KEY"] = packet["artifact_key"]
    prior_exports = {}
    for item in packet.get("prior_exports", []):
        identity = item["local_id"]
        if type(identity) is not int or identity in prior_exports:
            raise ValueError("Invalid prior export identity")
        prior_exports[identity] = base64.b64decode(item["content"], validate=True)
    directory = tempfile.mkdtemp(prefix="cronos-e2e-" + packet["run_id"] + "-", dir="/tmp")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from scripts.cleanup_e2e_run import cleanup
        result = asyncio.run(cleanup(packet["registry"], packet["run_id"], directory,
            execute=packet["mode"] == "cleanup", export_only=packet["mode"] == "export", prior_exports=prior_exports))
    for path in sorted(pathlib.Path(directory).iterdir()):
        if path.is_symlink() or not path.is_file() or not path.name.endswith(".zip.enc"):
            raise ValueError("Unexpected administrative export")
        exports.append({"name": path.name, "content": base64.b64encode(path.read_bytes()).decode()})
except Exception:
    result["status"] = "failed"
print(json.dumps({"result": result, "exports": exports, "export_directory": directory}, separators=(",", ":")))
`

// Owner-authorised vendor Testing Token for the UI registration challenge only.
// The production key never leaves the API container; only the token returns.
const testingTokenCode = `import json, os, sys, httpx
packet = json.load(sys.stdin)
out = {"testing_token": None}
try:
    if packet.get("mode") != "testing_token" or os.environ.get("RAILWAY_GIT_COMMIT_SHA") != packet["expected_revision"]:
        raise ValueError("Administrative revision mismatch")
    key = os.environ.get("CLERK_SECRET_KEY", "")
    if not key.startswith("sk_live_"):
        raise ValueError("Production provider credential required")
    response = httpx.post("https://api.clerk.com/v1/testing_tokens", headers={"Authorization": "Bearer " + key}, timeout=15)
    response.raise_for_status()
    out = {"testing_token": response.json()["token"]}
except Exception:
    pass
print(json.dumps(out, separators=(",", ":")))
`

async function railwayExecutable(environment) {
  if (environment.E2E_RAILWAY_CLI) return environment.E2E_RAILWAY_CLI
  if (process.platform !== 'win32') return 'railway'
  for (const directory of (process.env.PATH || '').split(delimiter)) {
    const path = join(directory, 'node_modules', '@railway', 'cli', 'bin', 'railway.exe')
    try { await access(path); return path } catch { /* Continue through installed command locations. */ }
  }
  throw new Error('Native Railway executable unavailable')
}

async function nativeTransport(packet, environment, code = remoteCode) {
  const temporary = await mkdtemp(join(tmpdir(), 'cronos-admin-ssh-'))
  try {
    const keyPath = join(temporary, 'identity')
    await writeFile(keyPath, environment.E2E_ADMIN_SSH_KEY, { mode: 0o600, flag: 'wx' })
    const executable = await railwayExecutable(environment)
    const command = `python -c 'exec(__import__("base64").b64decode("${Buffer.from(code).toString('base64')}"))'`
    const args = ['ssh', '--project', environment.E2E_RAILWAY_PROJECT_ID,
      '--environment', environment.E2E_RAILWAY_ENVIRONMENT_ID, '--service', environment.E2E_RAILWAY_API_SERVICE_ID,
      '--identity-file', keyPath, command]
    const inherited = Object.fromEntries(Object.entries(process.env).filter(([name]) => /^(PATH|PATHEXT|SYSTEMROOT|WINDIR|HOME|USERPROFILE|APPDATA|LOCALAPPDATA|TEMP|TMP)$/i.test(name)))
    const tokenName = environment.E2E_RAILWAY_TOKEN_TYPE === 'account' ? 'RAILWAY_API_TOKEN' : 'RAILWAY_TOKEN'
    const output = await new Promise((accept, reject) => {
      const child = spawn(executable, args, { windowsHide: true, shell: false,
        env: { ...inherited, [tokenName]: environment.E2E_RAILWAY_TOKEN }, stdio: ['pipe', 'pipe', 'pipe'] })
      let stdout = '', bytes = 0
      const timeout = setTimeout(() => { child.kill(); reject(new Error('Administrative transport timeout')) }, 300_000)
      child.stdout.on('data', chunk => {
        bytes += chunk.length
        if (bytes > 64 * 1024 * 1024) { child.kill(); reject(new Error('Administrative response exceeds limit')); return }
        stdout += chunk
      })
      child.stderr.on('data', () => {})
      child.stdin.on('error', () => {})
      child.once('error', () => { clearTimeout(timeout); reject(new Error('Administrative transport unavailable')) })
      child.once('close', code => { clearTimeout(timeout); code === 0 ? accept(stdout) : reject(new Error('Administrative transport failed')) })
      child.stdin.end(JSON.stringify(packet))
    })
    return JSON.parse(output)
  } finally { await rm(temporary, { recursive: true, force: true }) }
}

function validateAdministrativeConfiguration({ runId, expectedRevision, exportOnly, usePriorExports }, environment) {
  if (typeof exportOnly !== 'boolean' || typeof usePriorExports !== 'boolean' || (exportOnly && usePriorExports)) throw new Error('Invalid administrative export mode')
  if (!/^[a-z0-9-]+$/.test(runId || '') || !/^[a-f0-9]{40}$/.test(expectedRevision || '')) throw new Error('Invalid campaign identity')
  for (const name of ['E2E_REGISTRY_HMAC_KEY', 'E2E_ARTIFACT_KEY', 'E2E_ADMIN_SSH_KEY', 'E2E_RAILWAY_TOKEN', 'E2E_RAILWAY_PROJECT_ID', 'E2E_RAILWAY_ENVIRONMENT_ID', 'E2E_RAILWAY_API_SERVICE_ID']) {
    if (!environment[name]) throw new Error('Administrative dependency unavailable')
  }
  if (!['account', 'project'].includes(environment.E2E_RAILWAY_TOKEN_TYPE)) throw new Error('Invalid Railway token type')
  for (const name of ['E2E_REGISTRY_HMAC_KEY', 'E2E_ARTIFACT_KEY']) {
    const key = Buffer.from(environment[name], 'base64')
    if (key.length !== 32 || key.toString('base64') !== environment[name]) throw new Error('Invalid administrative protection key')
  }
}

export async function mintClerkTestingToken({ expectedRevision }, environment, { execute = nativeTransport } = {}) {
  if (!/^[a-f0-9]{40}$/.test(expectedRevision || '')) throw new Error('Invalid campaign identity')
  for (const name of ['E2E_ADMIN_SSH_KEY', 'E2E_RAILWAY_TOKEN', 'E2E_RAILWAY_PROJECT_ID', 'E2E_RAILWAY_ENVIRONMENT_ID', 'E2E_RAILWAY_API_SERVICE_ID']) {
    if (!environment[name]) throw new Error('Administrative dependency unavailable')
  }
  if (!['account', 'project'].includes(environment.E2E_RAILWAY_TOKEN_TYPE)) throw new Error('Invalid Railway token type')
  const token = (await execute({ mode: 'testing_token', expected_revision: expectedRevision }, environment, testingTokenCode))?.testing_token
  if (!/^[A-Za-z0-9_-]{20,200}$/.test(token || '')) throw new Error('Testing token unavailable')
  return token
}

async function inspectArtifactRoot(artifactRoot) {
  for (let parent = dirname(resolve(artifactRoot)); ; parent = dirname(parent)) {
    const parentInfo = await lstat(parent)
    if (!parentInfo.isDirectory() || parentInfo.isSymbolicLink()) throw new Error('Administrative artifact parent is not confined')
    if (parent === dirname(parent)) break
  }
  const existingRoot = await lstat(resolve(artifactRoot)).catch(error => { if (error.code !== 'ENOENT') throw error; return null })
  if (existingRoot && (!existingRoot.isDirectory() || existingRoot.isSymbolicLink())) throw new Error('Administrative artifact root is not confined')
  return existingRoot
}

async function readPriorExports({ artifactRoot, existingRoot, organizations, runId, usePriorExports }, environment) {
  const prior = new Map()
  if (usePriorExports && existingRoot) {
    for (const local_id of organizations) {
      const name = `organization-${local_id}.zip.enc`
      const path = join(artifactRoot, name)
      const file = await lstat(path).catch(error => { if (error.code !== 'ENOENT') throw error; return null })
      if (!file) continue
      if (!file.isFile() || file.isSymbolicLink() || file.size > 64 * 1024 * 1024) throw new Error('Prior administrative export is not confined')
      const content = await readFile(path)
      recoverEvidence(content, Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64'), { run_id: runId, path: name.slice(0, -4) })
      prior.set(name, { local_id, content })
    }
  }
  return prior
}

function validateExportOnlyOutcome(result, organizations, actors) {
  if (result.completed.length || result.removed_actors.length || !Array.isArray(result.exported)
    || new Set(result.exported).size !== result.exported.length || result.exported.some(id => !organizations.includes(id))
    || result.pending.length !== organizations.length || result.pending_actors.length !== actors.length
    || (result.status === 'exported' && result.exported.length !== organizations.length)) throw new Error('Administrative export cannot certify deletion')
}

function validateAdministrativeOutcome(result, { registry, runId, organizations, actors, exportOnly }) {
  if (!result || result.run_id !== runId || !(exportOnly ? ['exported', 'failed'] : ['completed', 'failed']).includes(result.status)) throw new Error('Administrative result identity mismatch')
  const persistentActors = new Set(registry.organizations.filter(item => item.type === 'persistent').flatMap(item => item.actors.map(actor => actor.id)))
  for (const [field, allowed] of [['completed', organizations], ['pending', organizations], ['removed_actors', actors], ['pending_actors', actors]]) {
    if (!Array.isArray(result[field]) || new Set(result[field]).size !== result[field].length || result[field].some(id => !allowed.includes(id))) throw new Error('Administrative target mismatch')
  }
  if (result.removed_actors.some(id => persistentActors.has(id) || result.pending_actors.includes(id)) || result.completed.some(id => result.pending.includes(id))) throw new Error('Administrative ownership conflict')
  if (organizations.some(id => !result.completed.includes(id) && !result.pending.includes(id))) throw new Error('Administrative target outcome missing')
  if (result.status === 'completed' && (result.pending.length || result.pending_actors.length || organizations.some(id => !result.completed.includes(id)))) throw new Error('Administrative cleanup remains pending')
  if (exportOnly) validateExportOnlyOutcome(result, organizations, actors)
}

function authenticateAdministrativeExports(response, result, { registry, organizations, actors, runId, exportOnly }, environment) {
  if (!Array.isArray(response.exports)) throw new Error('Administrative exports unavailable')
  const names = new Set()
  const authenticated = response.exports.map(item => {
    const allowed = organizations.map(id => `organization-${id}.zip.enc`).concat(actors.map(id => `actor-${id}.zip.enc`))
    if (!allowed.includes(item.name) || names.has(item.name) || typeof item.content !== 'string') throw new Error('Administrative export identity mismatch')
    names.add(item.name)
    const content = Buffer.from(item.content, 'base64')
    if (content.toString('base64') !== item.content) throw new Error('Invalid administrative export encoding')
    recoverEvidence(content, Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64'), { run_id: runId, path: item.name.slice(0, -4) })
    return { name: item.name, content }
  })
  if (result.completed.some(id => !names.has(`organization-${id}.zip.enc`))) throw new Error('Completed deletion lacks its authenticated export')
  if (exportOnly && result.exported.some(id => !names.has(`organization-${id}.zip.enc`))) throw new Error('Observed export lacks its authenticated backup')
  for (const id of result.removed_actors) {
    const covered = registry.organizations.some(school => result.completed.includes(school.local_id) && school.actors.some(actor => actor.id === id))
    if (!covered && !names.has(`actor-${id}.zip.enc`)) throw new Error('Removed orphan actor lacks its authenticated export')
  }
  return { names, authenticated }
}

async function persistAdministrativeExports(artifactRoot, authenticated, prior, failure) {
  await mkdir(resolve(artifactRoot), { recursive: true, mode: 0o700 })
  const rootInfo = await lstat(resolve(artifactRoot))
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) throw new Error('Administrative artifact root is not confined')
  for (const item of authenticated) {
    const path = join(artifactRoot, item.name)
    if (prior.has(item.name)) {
      const current = await lstat(path)
      if (!current.isFile() || current.isSymbolicLink() || !item.content.equals(prior.get(item.name).content)
        || !(await readFile(path)).equals(item.content)) throw new Error('Authenticated prior export changed')
    } else await writeFile(path, item.content, { mode: 0o600, flag: 'wx' })
    failure.exports.push(item.name)
  }
}

// A resolved intent is gone from the journal; anything left is an unobserved
// creation that the remote wrapper must never guess at. A malformed array is
// treated as unresolved rather than ignored.
function unresolvedIntentReport(registry) {
  try { return { intents: unresolvedUiCreationIntents(registry), invalid: false } }
  catch { return { intents: [], invalid: true } }
}

function hasUnresolvedUiCreation({ intents, invalid }) {
  return Boolean(intents.length || invalid)
}

// Confirmed removals and backups are preserved, but an unresolved creation
// keeps the whole campaign failed. An existing remote failure class stays first.
function withUnresolvedUiCreation(outcome, { intents, invalid }) {
  if (!intents.length && !invalid) return outcome
  outcome.status = 'failed'
  outcome.failure_type = outcome.failure_type ?? 'UnresolvedUiCreation'
  outcome.unresolved_intents = intents
  return outcome
}

export async function cleanupProductionCampaign({ registryPath, runId, expectedRevision, artifactRoot }, environment, { execute = nativeTransport, exportOnly = false, usePriorExports = false } = {}) {
  const failure = { run_id: runId, status: 'failed', completed: [], removed_actors: [], pending: [], pending_actors: [], failure_type: 'AdministrativeCleanupFailed' }
  let unresolved = { intents: [], invalid: false }
  try {
    validateAdministrativeConfiguration({ runId, expectedRevision, exportOnly, usePriorExports }, environment)
    const info = await lstat(registryPath)
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('Registry must be a regular file')
    const envelope = JSON.parse(await readFile(registryPath, 'utf8'))
    const registry = verifyRegistry(envelope, Buffer.from(environment.E2E_REGISTRY_HMAC_KEY, 'base64'))
    if (registry.schema_version !== 1 || registry.run_id !== runId || !Array.isArray(registry.organizations) || !Array.isArray(registry.actors)) throw new Error('Administrative registry identity mismatch')
    if (registry.organizations.some(item => !Number.isSafeInteger(item.local_id) || item.local_id <= 0 || !['disposable', 'persistent'].includes(item.type)) || registry.actors.some(item => !/^user_[a-zA-Z0-9]+$/.test(item.id || ''))) throw new Error('Invalid administrative target identity')
    unresolved = unresolvedIntentReport(registry)
    if (hasUnresolvedUiCreation(unresolved)) failure.unresolved_intents = unresolved.intents
    const organizations = registry.organizations.filter(item => item.type === 'disposable').map(item => item.local_id)
    const actors = registry.actors.map(item => item.id)
    failure.pending = [...organizations]
    failure.pending_actors = [...actors]
    if (new Set(organizations).size !== organizations.length || new Set(actors).size !== actors.length) throw new Error('Duplicate administrative identity')
    if (!organizations.length && !actors.length) {
      const empty = { ...failure, status: exportOnly ? 'exported' : 'completed', exports: [], ...(exportOnly ? { exported: [] } : {}), failure_type: undefined }
      return hasUnresolvedUiCreation(unresolved) ? withUnresolvedUiCreation(empty, unresolved) : empty
    }
    const existingRoot = await inspectArtifactRoot(artifactRoot)
    const prior = await readPriorExports({ artifactRoot, existingRoot, organizations, runId, usePriorExports }, environment)
    const response = await execute({ run_id: runId, expected_revision: expectedRevision, registry: envelope, mode: exportOnly ? 'export' : 'cleanup',
      prior_exports: [...prior.values()].map(({ local_id, content }) => ({ local_id, content: content.toString('base64') })),
      signing_key: environment.E2E_REGISTRY_HMAC_KEY, artifact_key: environment.E2E_ARTIFACT_KEY }, environment)
    const result = response?.result
    if (typeof response?.export_directory === 'string' && new RegExp(`^/tmp/cronos-e2e-${runId}-[a-zA-Z0-9_-]+$`).test(response.export_directory)) failure.remote_export_directory = response.export_directory
    validateAdministrativeOutcome(result, { registry, runId, organizations, actors, exportOnly })
    const { names, authenticated } = authenticateAdministrativeExports(response, result, { registry, organizations, actors, runId, exportOnly }, environment)
    // Preserve confirmed remote effects if local evidence persistence fails.
    Object.assign(failure, { completed: [...result.completed], removed_actors: [...result.removed_actors],
      pending: [...result.pending], pending_actors: [...result.pending_actors], exports: [] })
    await persistAdministrativeExports(artifactRoot, authenticated, prior, failure)
    const outcome = { run_id: runId, status: result.status, completed: result.completed, removed_actors: result.removed_actors,
      pending: result.pending, pending_actors: result.pending_actors, exports: [...names],
      ...(exportOnly ? { exported: [...result.exported] } : {}),
      ...(failure.remote_export_directory ? { remote_export_directory: failure.remote_export_directory } : {}),
      ...(result.status === 'failed' ? { failure_type: 'AdministrativeCleanupFailed' } : {}) }
    return withUnresolvedUiCreation(outcome, unresolved)
  } catch { return failure }
}
