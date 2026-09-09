export const PENDING_ORGANIZATION_STORAGE_PREFIX = 'cronos:pending-organization'

export function getPendingOrganizationKey(userId) {
  return userId ? `${PENDING_ORGANIZATION_STORAGE_PREFIX}:${userId}` : null
}

function safeInternalReturnPath(value) {
  return typeof value === 'string'
    && value.startsWith('/')
    && !value.startsWith('//')
    && !value.includes('://')
    ? value
    : null
}

export async function activateAndBootstrapOrganization(input, ports) {
  if (input.acceptance_confirmed !== true) {
    throw new Error('Confirme a aceitação dos documentos legais antes de continuar.')
  }

  const storageKey = getPendingOrganizationKey(input.userId)
  let organizationId = input.organizationId || (storageKey ? ports.storage.get(storageKey) : null)
  if (!organizationId) {
    if (!storageKey) throw new Error('A user identity is required to create an organization.')
    const name = typeof input.name === 'string' ? input.name.trim() : ''
    if (!name) throw new Error('Indique o nome da escola.')
    const organization = await ports.createOrganization({ name })
    organizationId = organization.id
  }
  if (storageKey) ports.storage.set(storageKey, organizationId)

  await ports.setActive({ organization: organizationId })
  const token = await ports.getToken({ organizationId, skipCache: true })
  if (!token) throw new Error('A fresh organization session token could not be created.')
  const result = await ports.bootstrap(token)
  const legalStatus = await ports.getLegalStatus(token)
  if (!legalStatus?.terms_version || !legalStatus?.dpa_version || !legalStatus?.privacy_version) {
    throw new Error('As versões legais não estão disponíveis. Atualize a página e tente novamente.')
  }
  const acceptance = await ports.acceptLegalDocuments(token, {
    acceptance_confirmed: true,
    terms_version: legalStatus.terms_version,
    dpa_version: legalStatus.dpa_version,
    privacy_version: legalStatus.privacy_version,
  })
  await ports.cacheMember(organizationId, result)
  await ports.cacheLegalStatus(organizationId, {
    accepted: true,
    requires_acceptance: false,
    terms_version: legalStatus.terms_version,
    dpa_version: legalStatus.dpa_version,
    privacy_version: legalStatus.privacy_version,
    accepted_at: acceptance.accepted_at,
  })
  if (storageKey) ports.storage.remove(storageKey)
  const isComplete = result.foundation_status === 'COMPLETED'
  const requestedRoute = safeInternalReturnPath(input.returnPath)
  ports.navigate(isComplete ? (requestedRoute || ports.defaultRoute(result.member)) : '/foundation')
  return result
}

export function sessionStoragePort(storage = window.sessionStorage) {
  return {
    get: (key) => storage.getItem(key),
    set: (key, value) => storage.setItem(key, value),
    remove: (key) => storage.removeItem(key),
  }
}
