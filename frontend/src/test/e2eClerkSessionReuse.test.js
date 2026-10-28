import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ signIn: vi.fn(), setupToken: vi.fn() }))

vi.mock('@clerk/testing/playwright', () => ({
  clerk: { signIn: mocks.signIn },
  setupClerkTestingToken: mocks.setupToken,
}))

vi.mock('../../e2e/utils/clerk-rate-limit.js', () => ({
  observeClerkSignIn: async (operation) => {
    await operation()
    return true
  },
}))

vi.mock('@playwright/test', () => ({
  expect: {
    poll: (operation) => ({
      toBe: async (expected) => {
        const value = await operation()
        if (value !== expected) throw new Error(`poll expected ${expected} but received ${value}`)
      },
    }),
  },
}))

import { loginAsAdminReal } from '../../e2e/utils/clerk-helpers.js'

// Runs in the native node project; the helper only needs a plain window object.
globalThis.window ??= {}

const ADMIN_EMAIL = 'admin+clerk_test@example.com'
const ORG_ID = 'org_test'

function fakeClerk({ email, organizationId }) {
  const clerk = {
    loaded: true,
    session: null,
    user: { primaryEmailAddress: { emailAddress: email } },
    organization: organizationId ? { id: organizationId } : null,
    __sessionWhenActivated: null,
    setActive: vi.fn(async ({ organization }) => {
      clerk.__sessionWhenActivated = clerk.session
      clerk.organization = { id: organization }
    }),
  }
  return clerk
}

function makePage() {
  return {
    goto: vi.fn(async () => {}),
    evaluate: vi.fn(async (callback, argument) => callback(argument)),
    waitForFunction: vi.fn(async (predicate, argument) => {
      for (let attempt = 0; attempt < 50; attempt += 1) {
        if (predicate(argument)) return
        await new Promise((resolve) => { setTimeout(resolve, 0) })
      }
      throw new Error('Clerk wait predicate never became true')
    }),
  }
}

describe('E2E Clerk login helper', () => {
  beforeEach(() => {
    vi.stubEnv('E2E_CLERK_ADMIN_EMAIL', ADMIN_EMAIL)
    vi.stubEnv('E2E_CLERK_ORG_ID', ORG_ID)
    mocks.signIn.mockReset()
    mocks.setupToken.mockReset()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete globalThis.window.Clerk
  })

  it('reuses a matching session without signing in or switching organizations again', async () => {
    window.Clerk = fakeClerk({ email: ADMIN_EMAIL, organizationId: ORG_ID })
    const page = makePage()

    await loginAsAdminReal(page)

    expect(mocks.signIn).not.toHaveBeenCalled()
    expect(window.Clerk.setActive).not.toHaveBeenCalled()
    expect(page.goto).toHaveBeenCalledTimes(2)
  })

  it('signs in when the stored identity differs', async () => {
    window.Clerk = fakeClerk({ email: 'other+clerk_test@example.com', organizationId: ORG_ID })
    mocks.signIn.mockImplementation(async () => {
      window.Clerk.user = { primaryEmailAddress: { emailAddress: ADMIN_EMAIL } }
      window.Clerk.session = {}
    })
    const page = makePage()

    await loginAsAdminReal(page)

    expect(mocks.signIn).toHaveBeenCalledWith({ page, emailAddress: ADMIN_EMAIL })
  })

  it('activates the test organization on a public page before entering a guarded route', async () => {
    window.Clerk = fakeClerk({ email: ADMIN_EMAIL, organizationId: 'org_previous' })
    window.Clerk.session = {}
    const page = makePage()
    page.goto.mockImplementation(async url => {
      if (!url.endsWith('/privacidade') && window.Clerk.organization.id !== ORG_ID) {
        throw new Error('The previous organization cannot access this test database')
      }
    })

    await loginAsAdminReal(page)

    expect(page.goto.mock.calls[0][0]).toMatch(/\/privacidade$/)
    expect(window.Clerk.setActive).toHaveBeenCalledWith({ organization: ORG_ID })
    expect(page.goto.mock.calls[1][0]).toMatch(/\/dashboard$/)
  })

  it('waits for the reloaded Clerk session before activating the organization', async () => {
    window.Clerk = fakeClerk({ email: 'other+clerk_test@example.com', organizationId: null })
    mocks.signIn.mockImplementation(async () => {
      // Clerk exposes the session only after its reload, not on the sign-in tick.
      setTimeout(() => {
        window.Clerk.user = { primaryEmailAddress: { emailAddress: ADMIN_EMAIL } }
        window.Clerk.session = {}
      }, 5)
    })
    const page = makePage()

    await loginAsAdminReal(page)

    expect(window.Clerk.setActive).toHaveBeenCalledWith({ organization: ORG_ID })
    expect(window.Clerk.__sessionWhenActivated).toBeTruthy()
  })
})
