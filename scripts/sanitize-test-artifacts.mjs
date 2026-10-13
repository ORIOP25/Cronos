import { readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const TEXT_EXTENSIONS = new Set(['.json', '.xml', '.txt', '.log', '.html', '.trace'])
const AUTH_STATE_NAME = /(?:storage[-_]?state|auth[-_]?state|\.auth)/i
const PLAYWRIGHT_TRACE_NAME = /^trace\.zip$/i
const SECRET_NAME = /(?:SECRET|TOKEN|PASSWORD|KEY|AUTHORIZATION|COOKIE|DATABASE_URL)/i

export function redactSecrets(content, secrets) {
  return [...new Set(secrets.filter((value) => typeof value === 'string' && value.length > 0))]
    .sort((left, right) => right.length - left.length)
    .reduce((result, secret) => result.split(secret).join('[REDACTED]'), content)
}

// Every configured credential of the CI job, by variable name.
export function configuredSecrets(environment) {
  return [...new Set(Object.entries(environment)
    .filter(([name, value]) => value && SECRET_NAME.test(name))
    .map(([, value]) => value))]
}

// Uploaded CI artifacts never keep sessions or traces, and text keeps no credential.
export async function sanitizeDirectory(directory, secrets) {
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
    if (AUTH_STATE_NAME.test(entry.name) || PLAYWRIGHT_TRACE_NAME.test(entry.name)) {
      await rm(path, { force: true, recursive: entry.isDirectory() })
      return
    }
    if (entry.isDirectory()) return sanitizeDirectory(path, secrets)
    if (!TEXT_EXTENSIONS.has(extname(entry.name).toLowerCase())) return
    const before = await readFile(path, 'utf8')
    const after = redactSecrets(before, secrets)
    if (after !== before) await writeFile(path, after)
  }))
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const secrets = configuredSecrets(process.env)
  await Promise.all(process.argv.slice(2).map((directory) => sanitizeDirectory(directory, secrets)))
}
