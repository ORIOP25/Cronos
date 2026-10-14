const DEFAULT_STORAGE_TTL_MS = 30 * 24 * 60 * 60 * 1000

export function readExpiringValue(storage, key, now = Date.now()) {
  if (!storage || !key) return null
  try {
    const raw = storage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !('value' in parsed) || !Number.isFinite(parsed.expiresAt)) {
      storage.removeItem(key)
      return null
    }
    if (parsed.expiresAt <= now) {
      storage.removeItem(key)
      return null
    }
    return parsed.value
  } catch {
    try { storage.removeItem(key) } catch { /* storage is optional */ }
    return null
  }
}

export function writeExpiringValue(storage, key, value, ttlMs = DEFAULT_STORAGE_TTL_MS, now = Date.now()) {
  if (!storage || !key || !Number.isFinite(ttlMs) || ttlMs <= 0) return false
  try {
    storage.setItem(key, JSON.stringify({ value, expiresAt: now + ttlMs }))
    return true
  } catch {
    return false
  }
}

export function clearStorageKeys(storage, predicate) {
  if (!storage || typeof predicate !== 'function') return 0
  const keys = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key && predicate(key)) keys.push(key)
  }
  keys.forEach((key) => storage.removeItem(key))
  return keys.length
}
