export const E2E_BASE_URL =
  process.env.BASE_URL || 'http://localhost:5174'

export function createE2eRunKey(length = 12) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz'
  return Array.from({ length }, () => (
    alphabet[Math.floor(Math.random() * alphabet.length)]
  )).join('')
}
