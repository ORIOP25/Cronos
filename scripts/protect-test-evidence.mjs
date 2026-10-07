import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto'
import { lstat, mkdir, readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

function authenticatedMetadata(metadata) {
  const path = metadata?.path
  if (typeof path !== 'string' || /[\\:\u0000]/.test(path) || path.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new Error('Evidence path must be a confined relative POSIX path')
  }
  if (typeof metadata.run_id !== 'string' || !metadata.run_id) throw new Error('Evidence run_id is required')
  return Buffer.from(JSON.stringify({ version: 1, run_id: metadata.run_id, path }))
}

function validateKey(key) {
  if (!Buffer.isBuffer(key) || key.length !== 32) throw new Error('Evidence key must contain exactly 32 bytes')
}

export function protectEvidence(content, key, metadata) {
  validateKey(key)
  const aad = authenticatedMetadata(metadata)
  const nonce = randomBytes(12)
  const cipher = createCipheriv('aes-256-gcm', key, nonce)
  cipher.setAAD(aad)
  const ciphertext = Buffer.concat([cipher.update(content), cipher.final()])
  return Buffer.from(JSON.stringify({ version: 1, nonce: nonce.toString('base64'), tag: cipher.getAuthTag().toString('base64'), ciphertext: ciphertext.toString('base64') }))
}

export function recoverEvidence(envelope, key, metadata) {
  validateKey(key)
  const aad = authenticatedMetadata(metadata)
  const decoded = JSON.parse(envelope.toString('utf8'))
  if (decoded.version !== 1) throw new Error('Unsupported evidence envelope')
  const nonce = Buffer.from(decoded.nonce, 'base64')
  const tag = Buffer.from(decoded.tag, 'base64')
  if (nonce.length !== 12 || tag.length !== 16) throw new Error('Invalid evidence envelope')
  const decipher = createDecipheriv('aes-256-gcm', key, nonce)
  decipher.setAAD(aad)
  decipher.setAuthTag(tag)
  return Buffer.concat([decipher.update(Buffer.from(decoded.ciphertext, 'base64')), decipher.final()])
}

export async function recoverEvidenceFile(source, destinationRoot, key, metadata) {
  const content = recoverEvidence(await readFile(source), key, metadata)
  let directory = resolve(destinationRoot)
  await mkdir(directory, { recursive: true })
  const segments = metadata.path.split('/')
  for (let index = 0; index < segments.length; index += 1) {
    const info = await lstat(directory)
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error('Evidence recovery directory must not be a symbolic link')
    if (index === segments.length - 1) {
      const destination = join(directory, segments[index])
      await writeFile(destination, content, { flag: 'wx', mode: 0o600 })
      return destination
    }
    directory = join(directory, segments[index])
    try { await mkdir(directory) } catch (error) { if (error.code !== 'EEXIST') throw error }
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [command, source, destinationRoot, runId, path, ...extra] = process.argv.slice(2)
  try {
    if (command !== 'recover' || !source || !destinationRoot || !runId || !path || extra.length) throw new Error('Usage: node scripts/protect-test-evidence.mjs recover <source.enc> <output-directory> <run-id> <original-relative-path>')
    const key = Buffer.from(process.env.E2E_ARTIFACT_KEY || '', 'base64')
    const destination = await recoverEvidenceFile(source, destinationRoot, key, { run_id: runId, path })
    console.log(`Recovered authenticated evidence: ${destination}`)
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
