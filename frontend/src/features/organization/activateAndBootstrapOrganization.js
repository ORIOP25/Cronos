export const PENDING_ORGANIZATION_KEY = 'cronos.pendingOrganizationActivation'

export async function activateAndBootstrapOrganization(input, ports) {
  let organizationId = input.organizationId || ports.storage.get(PENDING_ORGANIZATION_KEY)
  if (!organizationId) {
    const organization = await ports.createOrganization({ name: input.name.trim() })
    organizationId = organization.id
    ports.storage.set(PENDING_ORGANIZATION_KEY, organizationId)
  }

  await ports.setActive({ organization: organizationId })
  const token = await ports.getToken({ organizationId, skipCache: true })
  if (!token) throw new Error('A fresh organization session token could not be created.')
  const result = await ports.bootstrap(token)
  await ports.cacheMember(organizationId, result)
  ports.storage.remove(PENDING_ORGANIZATION_KEY)
  ports.navigate(result.onboarding_complete ? ports.defaultRoute(result.member) : '/onboarding')
  return result
}

export function sessionStoragePort(storage = window.sessionStorage) {
  return {
    get: (key) => storage.getItem(key),
    set: (key, value) => storage.setItem(key, value),
    remove: (key) => storage.removeItem(key),
  }
}
