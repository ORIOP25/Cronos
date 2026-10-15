/**
 * Revoke the pending organization invitation this E2E run created.
 *
 * A consumed (accepted) invitation is no longer pending, so there is nothing to
 * clean up and no by-id lookup is attempted. Listing keeps real list and revoke
 * errors visible: any failure propagates to the caller.
 *
 * Matching prefers the created invitation id, falling back to the run email, in
 * the spirit of backend/scripts/cleanup_e2e_clerk_invitations.py. Returns the
 * revoked invitation id, or null when there is nothing pending to clean up.
 */
export async function revokePendingInvitation(client, {
  organizationId,
  invitationId,
  email,
  requestingUserId,
}) {
  const invitations = await client.organizations.getOrganizationInvitationList({
    organizationId,
    status: ['pending'],
    limit: 100,
  })
  const pending = (invitations.data ?? []).find((invitation) => (
    (invitationId && invitation.id === invitationId)
    || (email && invitation.emailAddress === email)
  ))
  if (!pending) return null
  await client.organizations.revokeOrganizationInvitation({
    organizationId,
    invitationId: pending.id,
    requestingUserId,
  })
  return pending.id
}
