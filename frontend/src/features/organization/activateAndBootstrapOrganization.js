export const PENDING_ORGANIZATION_STORAGE_PREFIX = 'cronos:pending-organization'

export function getPendingOrganizationKey(userId) {
  return userId ? `${PENDING_ORGANIZATION_STORAGE_PREFIX}:${userId}` : null
}

export async function activateAndBootstrapOrganization(input, ports) {
  const storageKey = getPendingOrganizationKey(input.userId)
  let organizationId = input.organizationId || (storageKey ? ports.storage.get(storageKey) : null)
  if (!organizationId) {
    if (!storageKey) throw new Error('A user identity is required to create an organization.')
    const organization = await ports.createOrganization({ name: input.name.trim() })
    organizationId = organization.id
    ports.storage.set(storageKey, organizationId)
  }

  await ports.setActive({ organization: organizationId })
  const token = await ports.getToken({ organizationId, skipCache: true })
  if (!token) throw new Error('A fresh organization session token could not be created.')
  const result = await ports.bootstrap(token)
  await ports.cacheMember(organizationId, result)
  if (storageKey) ports.storage.remove(storageKey)
  const isComplete = result.foundation_status === 'COMPLETED'
  ports.navigate(isComplete ? ports.defaultRoute(result.member) : '/foundation')
  return result
}

export function sessionStoragePort(storage = window.sessionStorage) {
  return {
    get: (key) => storage.getItem(key),
    set: (key, value) => storage.setItem(key, value),
    remove: (key) => storage.removeItem(key),
  }
}
