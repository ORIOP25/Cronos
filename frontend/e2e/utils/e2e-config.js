import { randomUUID } from 'node:crypto'

export const E2E_BASE_URL =
  process.env.BASE_URL || 'http://127.0.0.1:5174'

export function createE2eRunKey(length = 12) {
  const entropy = randomUUID().replaceAll('-', '')
  const alphabet = 'abcdefghijklmnopqrstuvwxyz'
  return Array.from({ length }, (_, index) => (
    alphabet[Number.parseInt(entropy[index % entropy.length], 16) % alphabet.length]
  )).join('')
}
