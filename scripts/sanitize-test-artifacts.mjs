import { readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { extname, join } from 'node:path'

const TEXT_EXTENSIONS = new Set(['.json', '.xml', '.txt', '.log', '.html', '.trace'])
const SECRET_NAME = /(?:SECRET|TOKEN|PASSWORD|API_KEY|AUTHORIZATION|COOKIE|DATABASE_URL)/i
const AUTH_STATE_NAME = /(?:storage[-_]?state|auth[-_]?state|\.auth)/i
const PLAYWRIGHT_TRACE_NAME = /^trace\.zip$/i

export function redactSecrets(content, secrets) {
  return [...new Set(secrets.filter((value) => value && value.length >= 8))]
    .sort((left, right) => right.length - left.length)
    .reduce((result, secret) => result.split(secret).join('[REDACTED]'), content)
}

function environmentSecrets() {
  return Object.entries(process.env)
    .filter(([name, value]) => SECRET_NAME.test(name) && value)
    .map(([, value]) => value)
}

export async function sanitizeDirectory(directory, secrets) {
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch {
    return
  }
  await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name)
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

if (process.argv.length > 2) {
  const secrets = environmentSecrets()
  await Promise.all(process.argv.slice(2).map((directory) => sanitizeDirectory(directory, secrets)))
}
