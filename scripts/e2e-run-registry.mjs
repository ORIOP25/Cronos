import { createHmac, timingSafeEqual } from 'node:crypto'

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
