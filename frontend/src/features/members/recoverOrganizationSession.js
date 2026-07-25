export async function recoverOrganizationSession({ getToken, organizationId, requestMember }) {
  const token = await getToken({ organizationId, skipCache: true })
  if (!token) throw new Error('Não foi possível criar um token de sessão da organização.')
  return requestMember(token)
}
