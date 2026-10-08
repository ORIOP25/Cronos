import { createHmac, randomUUID, timingSafeEqual } from 'node:crypto'
import { lstat, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { isDeepStrictEqual } from 'node:util'

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

export function recordUiSchool(registry, observed, type, observedAt) {
  if (!['disposable', 'persistent'].includes(type)) throw new Error('Unknown UI school type')
  if (!Number.isSafeInteger(observed?.local_id) || observed.local_id <= 0 || !/^org_[a-zA-Z0-9]+$/.test(observed.clerk_id || '')) throw new Error('Invalid UI school identity')
  const creator = registry.actors?.find(actor => actor.id === observed.creator_id)
  if (!creator) throw new Error('UI school creator was not observed in this campaign')
  const checked = recordUiActor(registry, creator, observedAt)
  const created = timestamp(observed.created_at)
  if (created < timestamp(creator.created_at) || created > timestamp(observedAt)) throw new Error('UI school creation is outside the campaign')
  if (!Array.isArray(observed.actors) || !observed.actors.length || new Set(observed.actors.map(actor => actor.id)).size !== observed.actors.length) throw new Error('Invalid UI school member inventory')
  const actors = observed.actors.map(actor => {
    const registered = checked.actors.find(item => item.id === actor.id && item.email === actor.email)
    if (!registered) throw new Error('UI school member does not belong to this campaign')
    recordUiActor(checked, registered, observedAt)
    return { ...registered }
  })
  if (!actors.some(actor => actor.id === creator.id)) throw new Error('UI school creator is missing from its members')
  const school = {
    local_id: observed.local_id, clerk_id: observed.clerk_id, creator_id: creator.id,
    created_at: observed.created_at, creation_run_id: registry.run_id, provenance: 'ui', type, actors,
  }
  const previous = checked.organizations.find(item => item.local_id === school.local_id || item.clerk_id === school.clerk_id)
  if (previous && Object.entries(school).some(([field, value]) => field !== 'actors' && previous[field] !== value)) throw new Error('Observed UI school identity changed')
  return {
    ...checked,
    organizations: previous ? checked.organizations.map(item => item === previous ? school : item) : [...checked.organizations, school],
  }
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
  await updateUiRegistryFile(path, key, runId, registry => recordUiActor(registry, actor, observedAt))
}

export async function recordUiSchoolFile(path, key, runId, school, type, observedAt) {
  await updateUiRegistryFile(path, key, runId, registry => recordUiSchool(registry, school, type, observedAt))
}

async function updateUiRegistryFile(path, key, runId, update) {
  await realParents(path)
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('UI registry must be a regular file')
  const registry = verifyRegistry(JSON.parse(await readFile(path, 'utf8')), key)
  if (registry.run_id !== runId) throw new Error('UI registry run identity does not match')
  const envelope = signRegistry(update(registry), key)
  await writePrivateJson(path, envelope)
}

async function writePrivateJson(path, value) {
  const temporary = `${path}.${randomUUID()}.tmp`
  try {
    await writeFile(temporary, JSON.stringify(value), { flag: 'wx', mode: 0o600 })
    await rename(temporary, path)
  } finally { await rm(temporary, { force: true }) }
}

export async function retainPersistentSchoolFile(path, key, prepared, source) {
  const school = prepared?.organization
  if (prepared?.schema_version !== 1 || prepared.status !== 'prepared' || prepared.history_verified !== false
    || prepared.run_id !== source?.run_id || source?.organizations?.length !== 1
    || !isDeepStrictEqual(source.organizations[0], school) || school?.type !== 'persistent'
    || school.provenance !== 'ui' || school.creation_run_id !== source.run_id
    || !Number.isSafeInteger(school.local_id) || school.local_id <= 0 || !/^org_[a-zA-Z0-9]+$/.test(school.clerk_id || '')) throw new Error('Unconfirmed persistent UI preparation')
  await realParents(path)
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Persistent registry must be a regular file')
  const registry = verifyRegistry(JSON.parse(await readFile(path, 'utf8')), key)
  if (registry.schema_version !== 1 || !Array.isArray(registry.organizations)) throw new Error('Invalid persistent registry')
  const preparation = { ...prepared }
  delete preparation.organization
  const retained = { ...school, preparation }
  const existing = registry.organizations.filter(item => item.local_id === school.local_id || item.clerk_id === school.clerk_id)
  if (existing.length) {
    if (existing.length !== 1 || !isDeepStrictEqual(existing[0], retained)) throw new Error('Persistent school identity or preparation changed')
    return
  }
  await writePrivateJson(path, signRegistry({ ...registry, organizations: [...registry.organizations, retained] }, key))
}

// Acceptance runs with one worker; persist before a value can enter browser evidence.
export async function recordSecretFile(path, secret) {
  if (typeof secret !== 'string' || !secret) throw new Error('Dynamic secret must be a nonempty string')
  await realParents(path)
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Secret registry must be a regular file')
  const secrets = JSON.parse(await readFile(path, 'utf8'))
  if (!Array.isArray(secrets) || secrets.some(value => typeof value !== 'string')) throw new Error('Invalid secret registry')
  if (!secrets.includes(secret)) await writePrivateJson(path, [...secrets, secret])
}
