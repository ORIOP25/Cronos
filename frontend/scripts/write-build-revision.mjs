import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export function resolveBuildRevision(environment) {
  if (environment.CF_PAGES === '1') {
    const revision = environment.CF_PAGES_COMMIT_SHA
    if (!/^[a-f0-9]{40}$/.test(revision || '')) throw new Error('Cloudflare build revision must be a full SHA')
    return { schema_version: 1, revision, verifiable: true, source: 'cloudflare-pages' }
  }
  return { schema_version: 1, revision: null, verifiable: false, source: 'local' }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = resolve(dirname(fileURLToPath(import.meta.url)), '../dist')
  const identity = resolveBuildRevision(process.env)
  await mkdir(target, { recursive: true })
  await writeFile(resolve(target, 'revision.json'), `${JSON.stringify(identity)}\n`)
}
