// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import { revokePendingInvitation } from '../../e2e/utils/clerk-invitation-cleanup.js'

const ORGANIZATION_ID = 'org_test'
const REQUESTING_USER_ID = 'user_admin'

function createClient({ pending = [], listError = null, revokeError = null } = {}) {
  const revokeOrganizationInvitation = vi.fn(async () => {
    if (revokeError) throw revokeError
    return {}
  })
  const getOrganizationInvitationList = vi.fn(async () => {
    if (listError) throw listError
    return { data: pending }
  })
  const getOrganizationInvitation = vi.fn(async () => {
    throw new Error('getOrganizationInvitation must not be used for cleanup')
  })
  return {
    revokeOrganizationInvitation,
    getOrganizationInvitationList,
    getOrganizationInvitation,
    client: {
      organizations: {
        revokeOrganizationInvitation,
        getOrganizationInvitationList,
        getOrganizationInvitation,
      },
    },
  }
}

describe('revokePendingInvitation', () => {
  it('revokes only the created pending invitation without a by-id lookup', async () => {
    const created = { id: 'orginv_created', emailAddress: 'run+clerk_test@example.com' }
    const { client, revokeOrganizationInvitation, getOrganizationInvitation } = createClient({
      pending: [created],
    })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: created.id,
      email: created.emailAddress,
      requestingUserId: REQUESTING_USER_ID,
    })).resolves.toBe('orginv_created')

    expect(revokeOrganizationInvitation).toHaveBeenCalledWith({
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_created',
      requestingUserId: REQUESTING_USER_ID,
    })
    expect(getOrganizationInvitation).not.toHaveBeenCalled()
  })

  it('does nothing when the accepted invitation is absent from the pending list', async () => {
    const { client, revokeOrganizationInvitation, getOrganizationInvitation } = createClient({
      pending: [],
    })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_consumed',
      email: 'run+clerk_test@example.com',
      requestingUserId: REQUESTING_USER_ID,
    })).resolves.toBeNull()

    expect(revokeOrganizationInvitation).not.toHaveBeenCalled()
    expect(getOrganizationInvitation).not.toHaveBeenCalled()
  })

  it('leaves unrelated pending invitations untouched', async () => {
    const { client, revokeOrganizationInvitation } = createClient({
      pending: [{ id: 'orginv_other', emailAddress: 'other+clerk_test@example.com' }],
    })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_created',
      email: 'run+clerk_test@example.com',
      requestingUserId: REQUESTING_USER_ID,
    })).resolves.toBeNull()

    expect(revokeOrganizationInvitation).not.toHaveBeenCalled()
  })

  it('matches the created run by email when the id is unknown', async () => {
    const { client, revokeOrganizationInvitation } = createClient({
      pending: [
        { id: 'orginv_other', emailAddress: 'other+clerk_test@example.com' },
        { id: 'orginv_by_email', emailAddress: 'run+clerk_test@example.com' },
      ],
    })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_stale',
      email: 'run+clerk_test@example.com',
      requestingUserId: REQUESTING_USER_ID,
    })).resolves.toBe('orginv_by_email')

    expect(revokeOrganizationInvitation).toHaveBeenCalledWith({
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_by_email',
      requestingUserId: REQUESTING_USER_ID,
    })
  })

  it('propagates a pending-list failure without revoking', async () => {
    const failure = new Error('list failed')
    const { client, revokeOrganizationInvitation } = createClient({ listError: failure })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_created',
      email: 'run+clerk_test@example.com',
      requestingUserId: REQUESTING_USER_ID,
    })).rejects.toBe(failure)

    expect(revokeOrganizationInvitation).not.toHaveBeenCalled()
  })

  it('propagates a revoke failure', async () => {
    const failure = new Error('revoke failed')
    const { client } = createClient({
      pending: [{ id: 'orginv_created', emailAddress: 'run+clerk_test@example.com' }],
      revokeError: failure,
    })

    await expect(revokePendingInvitation(client, {
      organizationId: ORGANIZATION_ID,
      invitationId: 'orginv_created',
      email: 'run+clerk_test@example.com',
      requestingUserId: REQUESTING_USER_ID,
    })).rejects.toBe(failure)
  })
})
