// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import {
  activateAndBootstrapOrganization,
  getPendingOrganizationKey,
} from '../features/organization/activateAndBootstrapOrganization'


function ports(overrides = {}) {
  const values = new Map()
  return {
    createOrganization: vi.fn().mockResolvedValue({ id: 'org_new' }),
    setActive: vi.fn().mockResolvedValue(undefined),
    getToken: vi.fn().mockResolvedValue('fresh-token'),
    bootstrap: vi.fn().mockResolvedValue({
      organization: { id: 7 },
      member: { id: 8, capabilities: ['admin'] },
      foundation_status: 'NOT_STARTED',
    }),
    getLegalStatus: vi.fn().mockResolvedValue({
      accepted: false,
      requires_acceptance: true,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    }),
    acceptLegalDocuments: vi.fn().mockResolvedValue({
      id: 9,
      accepted_at: '2026-09-09T00:00:00Z',
    }),
    cacheMember: vi.fn().mockResolvedValue(undefined),
    cacheLegalStatus: vi.fn().mockResolvedValue(undefined),
    navigate: vi.fn(),
    defaultRoute: vi.fn(() => '/dashboard'),
    storage: {
      get: vi.fn((key) => values.get(key) || null),
      set: vi.fn((key, value) => values.set(key, value)),
      remove: vi.fn((key) => values.delete(key)),
    },
    ...overrides,
  }
}


describe('activateAndBootstrapOrganization', () => {
  const pendingKey = getPendingOrganizationKey('user_new')
  it('orders create, activation, fresh token, bootstrap, cache, and navigation', async () => {
    const calls = []
    const adapters = ports()
    for (const name of [
      'createOrganization', 'setActive', 'getToken', 'bootstrap', 'getLegalStatus',
      'acceptLegalDocuments', 'cacheMember', 'cacheLegalStatus', 'navigate',
    ]) {
      const original = adapters[name]
      adapters[name] = vi.fn(async (...args) => {
        calls.push(name)
        return original(...args)
      })
    }
    await activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new', acceptance_confirmed: true }, adapters)
    expect(calls).toEqual([
      'createOrganization', 'setActive', 'getToken', 'bootstrap', 'getLegalStatus',
      'acceptLegalDocuments', 'cacheMember', 'cacheLegalStatus', 'navigate',
    ])
    expect(adapters.getToken).toHaveBeenCalledWith({ organizationId: 'org_new', skipCache: true })
    expect(adapters.acceptLegalDocuments).toHaveBeenCalledWith('fresh-token', {
      acceptance_confirmed: true,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    })
    expect(adapters.navigate).toHaveBeenCalledWith('/foundation')
    expect(adapters.storage.remove).toHaveBeenCalledWith(pendingKey)
  })

  it('retries a stored organization without creating a duplicate', async () => {
    const adapters = ports()
    adapters.storage.get.mockReturnValue('org_pending')
    await activateAndBootstrapOrganization({ name: '', userId: 'user_new', acceptance_confirmed: true }, adapters)
    expect(adapters.createOrganization).not.toHaveBeenCalled()
    expect(adapters.setActive).toHaveBeenCalledWith({ organization: 'org_pending' })
  })

  it('keeps pending activation when bootstrap fails', async () => {
    const adapters = ports({ bootstrap: vi.fn().mockRejectedValue(new Error('offline')) })
    await expect(activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new', acceptance_confirmed: true }, adapters)).rejects.toThrow('offline')
    expect(adapters.storage.set).toHaveBeenCalledWith(pendingKey, 'org_new')
    expect(adapters.storage.remove).not.toHaveBeenCalled()
  })

  it('does not persist a phantom organization when creation itself fails', async () => {
    const adapters = ports({
      createOrganization: vi.fn().mockRejectedValue(new Error('create failed')),
    })

    await expect(activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new', acceptance_confirmed: true }, adapters)).rejects.toThrow('create failed')

    expect(adapters.storage.set).not.toHaveBeenCalled()
    expect(adapters.setActive).not.toHaveBeenCalled()
  })

  it.each(['setActive', 'getToken', 'cacheMember'])(
    'retains the created organization when %s fails',
    async (portName) => {
      const adapters = ports({
        [portName]: vi.fn().mockRejectedValue(new Error(`${portName} failed`)),
      })

      await expect(activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new', acceptance_confirmed: true }, adapters)).rejects.toThrow(`${portName} failed`)

      expect(adapters.storage.set).toHaveBeenCalledWith(pendingKey, 'org_new')
      expect(adapters.storage.remove).not.toHaveBeenCalled()
      expect(adapters.navigate).not.toHaveBeenCalled()
    },
  )

  it('navigates an already-onboarded member to the role default', async () => {
    const adapters = ports()
    adapters.bootstrap.mockResolvedValue({
      organization: { id: 7 },
      member: { id: 8, capabilities: ['admin'] },
      foundation_status: 'COMPLETED',
    })

    await activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new', acceptance_confirmed: true }, adapters)

    expect(adapters.defaultRoute).toHaveBeenCalledWith(expect.objectContaining({ id: 8 }))
    expect(adapters.navigate).toHaveBeenCalledWith('/dashboard')
  })

  it('requires the confirmation before creating the organization', async () => {
    const adapters = ports()
    await expect(activateAndBootstrapOrganization({ name: 'Cronos', userId: 'user_new' }, adapters))
      .rejects.toThrow(/Confirme a aceitação/)
    expect(adapters.createOrganization).not.toHaveBeenCalled()
  })
})
