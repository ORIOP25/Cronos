import { createHash } from 'node:crypto'
import { appendFileSync } from 'node:fs'
import { lstat, readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { evaluateAcceptance } from '../frontend/e2e/utils/acceptance-policy.js'
import { signRegistry, verifyRegistry } from './e2e-run-registry.mjs'
import { protectEvidenceFile, recoverEvidence } from './protect-test-evidence.mjs'
import { redactReport, sanitizeDirectory, TEXT_EXTENSIONS } from './sanitize-test-artifacts.mjs'

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

export async function finalizeRun(input, artifactRoot, { key, signingKey, secrets, registries = [] }) {
  if (!Array.isArray(secrets)) throw new Error('Explicit dynamic secret registry required')
  if (!Array.isArray(registries)) throw new Error('Registries must be an array')
  const run = JSON.parse(JSON.stringify(redactReport(input, secrets)))
  run.failures = [...(run.failures || [])]
  run.evidence_protected = false
  let artifacts = []
  let envelope = null
  let stage = 'keys'
  try {
    if (!Buffer.isBuffer(signingKey) || signingKey.length !== 32) throw new Error('Invalid manifest signing key')
    stage = 'root'
    await confinedRoot(artifactRoot)
    const protection = { key, runId: run.run_id }
    stage = 'registries'
    for (const registry of registries) {
      await protectEvidenceFile(registry?.source, join(artifactRoot, `${registry?.path}.enc`), key, { run_id: run.run_id, path: registry?.path })
    }
    stage = 'sanitize'
    await sanitizeDirectory(artifactRoot, secrets, protection)
    stage = 'inventory'
    artifacts = await inventory(artifactRoot, protection)
    stage = 'evidence'
    const files = new Set(artifacts.map(item => item.path))
    for (const item of run.cases || []) {
      item.evidence = (item.evidence || []).map(path => {
        if (typeof path !== 'string' || path.includes('\\') || path.includes(':') || path.includes(String.fromCharCode(0)) || path.split('/').some(part => !part || part === '.' || part === '..')) throw new Error('Invalid evidence path')
        const protectedPath = files.has(`${path}.enc`) ? `${path}.enc` : path
        if (!files.has(protectedPath)) throw new Error('Referenced evidence is missing')
        return protectedPath
      })
    }
    run.evidence_protected = true
    const assessment = evaluateAcceptance(run)
    stage = 'sign'
    envelope = signRegistry({ schema_version: 1, run, assessment, artifacts }, signingKey)
    return { run, assessment, artifacts, envelope }
  } catch {
    run.evidence_protected = false
    run.failures.push(`Artifact finalization failed: ${stage}`)
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

// Artifact integrity only: the wrapper that the workflow uploads must mirror the
// signed manifest, so an altered unsigned wrapper cannot be uploaded as
// authenticated evidence. This never certifies production.
export async function verifySignedResult(result, artifactRoot, { key, signingKey }) {
  if (!result?.envelope) throw new Error('Signed result envelope is required')
  const manifest = await verifyRunArtifacts(result.envelope, artifactRoot, { key, signingKey })
  const mirror = value => JSON.stringify(value)
  if (mirror(result.run) !== mirror(manifest.run)
    || mirror(result.assessment) !== mirror(manifest.assessment)
    || mirror(result.artifacts) !== mirror(manifest.artifacts)) {
    throw new Error('Result wrapper does not mirror the signed manifest')
  }
  return manifest
}

function outsideArtifacts(path, root) {
  const destination = relative(resolve(root), resolve(path))
  if (destination && (isAbsolute(destination) || destination === '..' || destination.startsWith(`..${sep}`))) return
  throw new Error('Private secret registry and final report must stay outside the artifact root')
}

function artifactKeys() {
  return {
    key: Buffer.from(process.env.E2E_ARTIFACT_KEY || '', 'base64'),
    signingKey: Buffer.from(process.env.E2E_REGISTRY_HMAC_KEY || '', 'base64'),
  }
}

// A reason enum keeps the CLI output safe: it never echoes keys, paths or raw
// exception text. Integrity only; the signed assessment stays incomplete or
// partial for preparation and diagnosis.
async function verifyCli(resultPath, artifactRoot) {
  let result
  try { result = JSON.parse(await readFile(resultPath, 'utf8')) } catch { return 'unreadable' }
  if (!result?.envelope) return 'unsigned'
  try {
    await verifySignedResult(result, resolve(artifactRoot), artifactKeys())
    return null
  } catch { return 'integrity' }
}

// A fixed receipt with enum values only: no URL, path, key or secret. It is
// written once outside the artifact root. An existing file is never overwritten,
// so a stale receipt can never be presented as the current verification.
async function writeVerificationReceipt(receiptPath, artifactRoot, reason) {
  const target = resolve(receiptPath)
  outsideArtifacts(target, artifactRoot)
  await confinedRoot(dirname(target))
  const receipt = { integrity: reason ? 'rejected' : 'verified', reason: reason ?? null, certifies_production: false }
  try {
    await writeFile(target, `${JSON.stringify(receipt, null, 2)}\n`, { flag: 'wx', mode: 0o600 })
    return true
  } catch (error) {
    if (error.code === 'EEXIST') return false
    throw error
  }
}

// The workflow reads one fixed boolean output. An absent output means false.
function emitReceiptAvailable() {
  const output = process.env.GITHUB_OUTPUT
  if (!output) return
  appendFileSync(output, 'receipt_available=true\n')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [command, ...rest] = process.argv.slice(2)
  if (command === 'verify') {
    const [resultPath, artifactRoot, receiptPath, ...extra] = rest
    if (!resultPath || !artifactRoot || extra.length) throw new Error('Usage: node scripts/finalize-real-browser-run.mjs verify <result.json> <artifacts> [<verification-receipt.json>]')
    const reason = await verifyCli(resultPath, artifactRoot)
    const available = receiptPath ? await writeVerificationReceipt(receiptPath, artifactRoot, reason) : false
    if (available) emitReceiptAvailable()
    if (receiptPath && !available) {
      console.error('Artifact integrity: receipt unavailable (conflict)')
      process.exitCode = 1
    } else if (reason) {
      console.error(`Artifact integrity: rejected (${reason})`)
      process.exitCode = 1
    } else {
      console.log('Artifact integrity: verified')
      process.exitCode = 0
    }
  } else {
    const [reportPath, artifactRoot, outputPath, secretRegistryPath, ...extra] = [command, ...rest]
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
}
