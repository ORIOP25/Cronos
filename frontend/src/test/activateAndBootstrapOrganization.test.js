import { describe, expect, it, vi } from 'vitest'
import {
  activateAndBootstrapOrganization,
  PENDING_ORGANIZATION_KEY,
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
      onboarding_complete: false,
    }),
    cacheMember: vi.fn().mockResolvedValue(undefined),
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
  it('orders create, activation, fresh token, bootstrap, cache, and navigation', async () => {
    const calls = []
    const adapters = ports()
    for (const name of ['createOrganization', 'setActive', 'getToken', 'bootstrap', 'cacheMember', 'navigate']) {
      const original = adapters[name]
      adapters[name] = vi.fn(async (...args) => {
        calls.push(name)
        return original(...args)
      })
    }
    await activateAndBootstrapOrganization({ name: 'Cronos' }, adapters)
    expect(calls).toEqual([
      'createOrganization', 'setActive', 'getToken', 'bootstrap', 'cacheMember', 'navigate',
    ])
    expect(adapters.getToken).toHaveBeenCalledWith({ organizationId: 'org_new', skipCache: true })
    expect(adapters.navigate).toHaveBeenCalledWith('/onboarding')
    expect(adapters.storage.remove).toHaveBeenCalledWith(PENDING_ORGANIZATION_KEY)
  })

  it('retries a stored organization without creating a duplicate', async () => {
    const adapters = ports()
    adapters.storage.get.mockReturnValue('org_pending')
    await activateAndBootstrapOrganization({ name: '' }, adapters)
    expect(adapters.createOrganization).not.toHaveBeenCalled()
    expect(adapters.setActive).toHaveBeenCalledWith({ organization: 'org_pending' })
  })

  it('keeps pending activation when bootstrap fails', async () => {
    const adapters = ports({ bootstrap: vi.fn().mockRejectedValue(new Error('offline')) })
    await expect(activateAndBootstrapOrganization({ name: 'Cronos' }, adapters)).rejects.toThrow('offline')
    expect(adapters.storage.set).toHaveBeenCalledWith(PENDING_ORGANIZATION_KEY, 'org_new')
    expect(adapters.storage.remove).not.toHaveBeenCalled()
  })

  it('does not persist a phantom organization when creation itself fails', async () => {
    const adapters = ports({
      createOrganization: vi.fn().mockRejectedValue(new Error('create failed')),
    })

    await expect(activateAndBootstrapOrganization({ name: 'Cronos' }, adapters)).rejects.toThrow('create failed')

    expect(adapters.storage.set).not.toHaveBeenCalled()
    expect(adapters.setActive).not.toHaveBeenCalled()
  })

  it.each(['setActive', 'getToken', 'cacheMember'])(
    'retains the created organization when %s fails',
    async (portName) => {
      const adapters = ports({
        [portName]: vi.fn().mockRejectedValue(new Error(`${portName} failed`)),
      })

      await expect(activateAndBootstrapOrganization({ name: 'Cronos' }, adapters)).rejects.toThrow(`${portName} failed`)

      expect(adapters.storage.set).toHaveBeenCalledWith(PENDING_ORGANIZATION_KEY, 'org_new')
      expect(adapters.storage.remove).not.toHaveBeenCalled()
      expect(adapters.navigate).not.toHaveBeenCalled()
    },
  )

  it('navigates an already-onboarded member to the role default', async () => {
    const adapters = ports()
    adapters.bootstrap.mockResolvedValue({
      organization: { id: 7 },
      member: { id: 8, capabilities: ['admin'] },
      onboarding_complete: true,
    })

    await activateAndBootstrapOrganization({ name: 'Cronos' }, adapters)

    expect(adapters.defaultRoute).toHaveBeenCalledWith(expect.objectContaining({ id: 8 }))
    expect(adapters.navigate).toHaveBeenCalledWith('/dashboard')
  })
})
