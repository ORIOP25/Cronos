import { createHmac, randomUUID, timingSafeEqual } from 'node:crypto'
import { lstat, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'

function timestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString() !== value) throw new Error('Invalid UI registry timestamp')
  return Date.parse(value)
}

export function createUiRegistry(runId, startedAt) {
  if (typeof runId !== 'string' || !/^[a-z0-9-]+$/.test(runId)) throw new Error('Invalid UI run identity')
  timestamp(startedAt)
  return { schema_version: 1, run_id: runId, started_at: startedAt, finished_at: startedAt, organizations: [], actors: [] }
}

export function recordUiActor(registry, observed, observedAt) {
  const started = timestamp(registry.started_at)
  const finished = timestamp(registry.finished_at)
  const checked = timestamp(observedAt)
  if (registry.schema_version !== 1 || finished < started || checked < finished || !Array.isArray(registry.actors) || !Array.isArray(registry.organizations)) throw new Error('Invalid UI registry timestamp or shape')
  const expected = createUiRegistry(registry.run_id, registry.started_at)
  if (!/^user_[a-zA-Z0-9]+$/.test(observed?.id || '') || !['admincronos100', 'professorcronos100'].some(base => observed.email === `${base}+${expected.run_id}@gmail.com`)) throw new Error('Actor identity does not belong to this UI run')
  const created = timestamp(observed.created_at)
  if (created < started || created > checked) throw new Error('Actor creation timestamp does not belong to this UI run')
  const actor = { id: observed.id, email: observed.email, created_at: observed.created_at, creation_run_id: registry.run_id, provenance: 'ui', type: 'disposable' }
  const previous = registry.actors.find(item => item.id === actor.id)
  if (previous && Object.entries(actor).some(([field, value]) => previous[field] !== value)) throw new Error('Observed actor identity changed')
  return { ...registry, finished_at: observedAt, actors: previous ? [...registry.actors] : [...registry.actors, actor] }
}

function signature(payload, key) {
  if (!Buffer.isBuffer(key) || key.length !== 32) throw new Error('Registry key must contain exactly 32 bytes')
  return createHmac('sha256', key).update(payload).digest()
}

export function signRegistry(registry, key) {
  if (!registry || typeof registry !== 'object' || Array.isArray(registry)) throw new Error('Invalid registry payload')
  const payload = Buffer.from(JSON.stringify(registry))
  return { version: 1, payload: payload.toString('base64'), signature: signature(payload, key).toString('hex') }
}

export function verifyRegistry(envelope, key) {
  if (envelope?.version !== 1 || typeof envelope.payload !== 'string' || !/^[a-f0-9]{64}$/.test(envelope.signature || '')) throw new Error('Invalid registry envelope')
  const payload = Buffer.from(envelope.payload, 'base64')
  if (payload.toString('base64') !== envelope.payload) throw new Error('Invalid registry encoding')
  if (!timingSafeEqual(signature(payload, key), Buffer.from(envelope.signature, 'hex'))) throw new Error('Invalid registry signature')
  const registry = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payload))
  if (!registry || typeof registry !== 'object' || Array.isArray(registry)) throw new Error('Invalid registry payload')
  return registry
}

async function realParents(path) {
  let directory = dirname(resolve(path))
  for (;;) {
    const info = await lstat(directory)
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('UI registry directory is not confined')
    const parent = dirname(directory)
    if (parent === directory) return
    directory = parent
  }
}

export async function createUiRegistryFile(path, key, runId, startedAt) {
  const envelope = signRegistry(createUiRegistry(runId, startedAt), key)
  await realParents(path)
  await writeFile(path, JSON.stringify(envelope), { flag: 'wx', mode: 0o600 })
}

export async function recordUiActorFile(path, key, runId, actor, observedAt) {
  await realParents(path)
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('UI registry must be a regular file')
  const registry = verifyRegistry(JSON.parse(await readFile(path, 'utf8')), key)
  if (registry.run_id !== runId) throw new Error('UI registry run identity does not match')
  const envelope = signRegistry(recordUiActor(registry, actor, observedAt), key)
  const temporary = `${path}.${randomUUID()}.tmp`
  try {
    await writeFile(temporary, JSON.stringify(envelope), { flag: 'wx', mode: 0o600 })
    await rename(temporary, path)
  } finally { await rm(temporary, { force: true }) }
}
