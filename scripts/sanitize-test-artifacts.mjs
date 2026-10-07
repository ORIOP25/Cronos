import { readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
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
    const after = redactSecrets(before, secrets)
    if (after !== before) await writeFile(path, after)
  }))
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dynamic = process.env.E2E_SECRET_REGISTRY
    ? JSON.parse(await readFile(process.env.E2E_SECRET_REGISTRY, 'utf8')) : []
  const secrets = acceptanceSecrets(process.env, dynamic)
  const protection = process.env.E2E_ARTIFACT_KEY
    ? { key: Buffer.from(process.env.E2E_ARTIFACT_KEY, 'base64'), runId: process.env.E2E_RUN_ID }
    : undefined
  await Promise.all(process.argv.slice(2).map((directory) => sanitizeDirectory(directory, secrets, protection)))
}
