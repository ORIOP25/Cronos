import { lstat, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { isDeepStrictEqual } from 'node:util'
import { protectEvidence, recoverEvidence } from './protect-test-evidence.mjs'
import { acceptanceSecrets } from './acceptance-run.mjs'

export const TEXT_EXTENSIONS = new Set(['.json', '.xml', '.txt', '.log', '.html', '.trace'])
const AUTH_STATE_NAME = /(?:storage[-_]?state|auth[-_]?state|\.auth)/i
const PLAYWRIGHT_TRACE_NAME = /^trace\.zip$/i

export function redactSecrets(content, secrets) {
  return [...new Set(secrets.filter((value) => typeof value === 'string' && value.length > 0))]
    .sort((left, right) => right.length - left.length)
    .reduce((result, secret) => result.split(secret).join('[REDACTED]'), content)
}

// The report redaction policy. It walks the parsed JSON tree so a decoded string
// leaf is redacted with the raw secret, an exact numeric secret becomes the
// redacted string, and field names stay unchanged. It never rewrites escaped
// JSON text, so the document stays well formed.
export function redactReport(value, secrets) {
  if (typeof value === 'string') return redactSecrets(value, secrets)
  if (typeof value === 'number') return secrets.includes(String(value)) ? '[REDACTED]' : value
  if (Array.isArray(value)) return value.map(item => redactReport(item, secrets))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, redactReport(item, secrets)]))
  }
  return value
}

// Production JSON evidence and diagnostics share this policy. A malformed
// document fails closed so no unsafe plain JSON is published. When the parsed
// value is unchanged the original text is returned byte-for-byte.
export function redactJsonText(content, secrets) {
  const parsed = JSON.parse(content)
  const redacted = redactReport(parsed, secrets)
  return isDeepStrictEqual(parsed, redacted) ? content : `${JSON.stringify(redacted, null, 2)}\n`
}

export async function sanitizeDirectory(directory, secrets, protection, root = directory) {
  if (protection && (!Buffer.isBuffer(protection.key) || protection.key.length !== 32 || !protection.runId)) {
    throw new Error('Production evidence requires a 32-byte key and run identity')
  }
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch (error) {
    if (error.code === 'ENOENT') return
    throw error
  }
  await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name)
    if (entry.isSymbolicLink()) throw new Error('Artifact symbolic links are forbidden')
    if (AUTH_STATE_NAME.test(entry.name) || (!protection && PLAYWRIGHT_TRACE_NAME.test(entry.name))) {
      await rm(path, { force: true, recursive: entry.isDirectory() })
      return
    }
    if (entry.isDirectory()) return sanitizeDirectory(path, secrets, protection, root)
    if (!TEXT_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
      if (protection) {
        const isEnvelope = extname(entry.name) === '.enc'
        const metadata = { run_id: protection.runId, path: relative(root, isEnvelope ? path.slice(0, -4) : path).replaceAll('\\', '/') }
        if (isEnvelope) recoverEvidence(await readFile(path), protection.key, metadata)
        else {
          const envelope = protectEvidence(await readFile(path), protection.key, metadata)
          await writeFile(`${path}.enc`, envelope, { flag: 'wx' })
          await rm(path)
        }
      }
      return
    }
    const before = await readFile(path, 'utf8')
    const after = protection && extname(entry.name).toLowerCase() === '.json'
      ? redactJsonText(before, secrets)
      : redactSecrets(before, secrets)
    if (after !== before) await writeFile(path, after)
  }))
}

// The sealed `acceptance-result.json` is immutable after the finalizer signs it
// (the run is already redacted before signing). These four diagnostics are the
// only files this step may touch; the sealed result uploads with the verified
// artifact root instead.
const DIAGNOSTIC_FILES = Object.freeze([
  'acceptance-plan.json', 'acceptance-cleanup.json', 'diagnostic-assessment.json', 'artifact-verification.json',
])

// Mirror the finalizer confinement walk: the diagnostics directory and every
// ancestor must be a real directory, never a symbolic link or junction. Only the
// four allowlisted base names are ever read or written.
async function confinedDirectory(directory) {
  let current = resolve(directory)
  for (;;) {
    const info = await lstat(current)
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error('Diagnostic directory is not confined')
    const parent = resolve(current, '..')
    if (parent === current) return
    current = parent
  }
}

// Only these four result/diagnostic JSON files may be redacted. The private UI
// journal and secret registries stay untouched even when they share the parent
// directory. A malformed document fails closed before any write. A document
// whose parsed value is unchanged keeps its exact bytes.
export async function sanitizeCampaignDiagnostics(directory, secrets) {
  try {
    await confinedDirectory(directory)
  } catch (error) {
    if (error.code === 'ENOENT') return
    throw error
  }
  for (const name of DIAGNOSTIC_FILES) {
    const path = join(directory, name)
    let info
    try {
      info = await lstat(path)
    } catch (error) {
      if (error.code === 'ENOENT') continue
      throw error
    }
    if (info.isSymbolicLink() || !info.isFile()) throw new Error('Diagnostic artifact is not a regular file')
    const before = await readFile(path, 'utf8')
    const after = redactJsonText(before, secrets)
    if (after !== before) await writeFile(path, after)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dynamic = process.env.E2E_SECRET_REGISTRY
    ? JSON.parse(await readFile(process.env.E2E_SECRET_REGISTRY, 'utf8')) : []
  const secrets = acceptanceSecrets(process.env, dynamic)
  const protection = process.env.E2E_ARTIFACT_KEY
    ? { key: Buffer.from(process.env.E2E_ARTIFACT_KEY, 'base64'), runId: process.env.E2E_RUN_ID }
    : undefined
  const args = process.argv.slice(2)
  if (args[0] === '--diagnostics') {
    const directories = args.slice(1)
    if (!directories.length) throw new Error('Usage: node scripts/sanitize-test-artifacts.mjs --diagnostics <directory>')
    for (const directory of directories) await sanitizeCampaignDiagnostics(directory, secrets)
  } else {
    await Promise.all(args.map((directory) => sanitizeDirectory(directory, secrets, protection)))
  }
}
