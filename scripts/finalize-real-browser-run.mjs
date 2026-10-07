import { createHash } from 'node:crypto'
import { lstat, readFile, readdir, writeFile } from 'node:fs/promises'
import { extname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { evaluateAcceptance } from '../frontend/e2e/utils/acceptance-policy.js'
import { signRegistry, verifyRegistry } from './e2e-run-registry.mjs'
import { recoverEvidence } from './protect-test-evidence.mjs'
import { redactSecrets, sanitizeDirectory, TEXT_EXTENSIONS } from './sanitize-test-artifacts.mjs'

async function confinedRoot(directory) {
  let current = resolve(directory)
  for (;;) {
    const info = await lstat(current)
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error('Artifact directory is not confined')
    const parent = resolve(current, '..')
    if (parent === current) return
    current = parent
  }
}

async function inventory(directory, protection, prefix = '') {
  const entries = await readdir(directory, { withFileTypes: true })
  const artifacts = []
  for (const entry of entries) {
    const path = prefix ? `${prefix}/${entry.name}` : entry.name
    if (entry.isSymbolicLink()) throw new Error('Artifact symbolic links are forbidden')
    if (entry.isDirectory()) { artifacts.push(...await inventory(join(directory, entry.name), protection, path)); continue }
    if (!entry.isFile()) throw new Error('Artifact is not a regular file')
    const content = await readFile(join(directory, entry.name))
    if (extname(path) === '.enc') recoverEvidence(content, protection.key, { run_id: protection.runId, path: path.slice(0, -4) })
    else if (!TEXT_EXTENSIONS.has(extname(path).toLowerCase())) throw new Error('Unprotected binary artifact')
    artifacts.push({ path, bytes: content.length, sha256: createHash('sha256').update(content).digest('hex') })
  }
  return artifacts.sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0)
}

export async function finalizeRun(input, artifactRoot, { key, signingKey, secrets }) {
  if (!Array.isArray(secrets)) throw new Error('Explicit dynamic secret registry required')
  const run = JSON.parse(redactSecrets(JSON.stringify(input), secrets))
  run.failures = [...(run.failures || [])]
  run.evidence_protected = false
  let artifacts = []
  let envelope = null
  try {
    if (!Buffer.isBuffer(signingKey) || signingKey.length !== 32) throw new Error('Invalid manifest signing key')
    await confinedRoot(artifactRoot)
    const protection = { key, runId: run.run_id }
    await sanitizeDirectory(artifactRoot, secrets, protection)
    artifacts = await inventory(artifactRoot, protection)
    const files = new Set(artifacts.map(item => item.path))
    for (const item of run.cases || []) {
      item.evidence = (item.evidence || []).map(path => {
        if (typeof path !== 'string' || /[\\:\u0000]/.test(path) || path.split('/').some(part => !part || part === '.' || part === '..')) throw new Error('Invalid evidence path')
        const protectedPath = files.has(`${path}.enc`) ? `${path}.enc` : path
        if (!files.has(protectedPath)) throw new Error('Referenced evidence is missing')
        return protectedPath
      })
    }
    run.evidence_protected = true
    const assessment = evaluateAcceptance(run)
    envelope = signRegistry({ schema_version: 1, run, assessment, artifacts }, signingKey)
    return { run, assessment, artifacts, envelope }
  } catch {
    run.failures.push('Artifact protection or evidence verification failed')
    return { run, assessment: evaluateAcceptance(run), artifacts: [], envelope }
  }
}

export async function verifyRunArtifacts(envelope, artifactRoot, { key, signingKey }) {
  const manifest = verifyRegistry(envelope, signingKey)
  await confinedRoot(artifactRoot)
  const observed = await inventory(artifactRoot, { key, runId: manifest.run.run_id })
  if (JSON.stringify(observed) !== JSON.stringify(manifest.artifacts)) throw new Error('Signed artifact inventory does not match the files')
  const assessment = evaluateAcceptance(manifest.run)
  if (JSON.stringify(assessment) !== JSON.stringify(manifest.assessment)) throw new Error('Signed assessment does not match the campaign')
  return manifest
}

function outsideArtifacts(path, root) {
  const destination = relative(resolve(root), resolve(path))
  if (destination && (isAbsolute(destination) || destination === '..' || destination.startsWith(`..${sep}`))) return
  throw new Error('Private secret registry and final report must stay outside the artifact root')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [reportPath, artifactRoot, outputPath, secretRegistryPath, ...extra] = process.argv.slice(2)
  if (!reportPath || !artifactRoot || !outputPath || !secretRegistryPath || extra.length) throw new Error('Usage: node scripts/finalize-real-browser-run.mjs <run.json> <artifacts> <result.json> <private-secrets.json>')
  outsideArtifacts(secretRegistryPath, artifactRoot)
  outsideArtifacts(outputPath, artifactRoot)
  const result = await finalizeRun(JSON.parse(await readFile(reportPath, 'utf8')), resolve(artifactRoot), {
    key: Buffer.from(process.env.E2E_ARTIFACT_KEY || '', 'base64'), signingKey: Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'),
    secrets: JSON.parse(await readFile(secretRegistryPath, 'utf8')),
  })
  await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx', mode: 0o600 })
  console.log(`Campaign result: ${result.assessment.status}`)
  if (result.assessment.status !== 'validated') process.exitCode = 1
}
