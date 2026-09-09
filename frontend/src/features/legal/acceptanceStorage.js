const LEGAL_ACCEPTANCE_STORAGE_PREFIX = 'cronos:legal-acceptance:'
const PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY = `${LEGAL_ACCEPTANCE_STORAGE_PREFIX}pending`

export function getLegalAcceptanceStorageKey(userId) {
  return userId ? `${LEGAL_ACCEPTANCE_STORAGE_PREFIX}${userId}` : null
}

function getSessionStorage() {
  return typeof window === 'undefined' ? null : window.sessionStorage
}

export function hasLegalAcceptance(userId, storage = getSessionStorage()) {
  const key = getLegalAcceptanceStorageKey(userId)
  if (!storage) return false
  if (key && storage.getItem(key) === 'true') return true
  if (storage.getItem(PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY) !== 'true') return false
  if (key) {
    storage.setItem(key, 'true')
    storage.removeItem(PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY)
  }
  return true
}

export function setLegalAcceptance(userId, accepted, storage = getSessionStorage()) {
  const key = getLegalAcceptanceStorageKey(userId)
  if (!storage) return
  if (accepted) {
    storage.setItem(key || PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY, 'true')
    if (key) storage.removeItem(PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY)
  } else {
    if (key) storage.removeItem(key)
    storage.removeItem(PENDING_LEGAL_ACCEPTANCE_STORAGE_KEY)
  }
}

export function clearLegalAcceptance(userId, storage = getSessionStorage()) {
  setLegalAcceptance(userId, false, storage)
}
