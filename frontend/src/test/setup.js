import '@testing-library/jest-dom'
import { vi } from 'vitest'

const DEFAULT_STATE = {
  isSignedIn: true,
  isLoaded: true,
  userId: 'user_test_123',
  role: 'org:admin',
  orgId: 1,
  orgName: 'Test Org',
  teacherId: null,
}

let _clerkState = { ...DEFAULT_STATE }
let _signInState = {
  signIn: null,
  errors: { fields: {} },
  fetchStatus: 'idle',
}

export function setClerkState(overrides = {}) {
  Object.assign(_clerkState, overrides)
}

export function resetClerkState() {
  _clerkState = { ...DEFAULT_STATE }
  _signInState = {
    signIn: null,
    errors: { fields: {} },
    fetchStatus: 'idle',
  }
}

export function setClerkSignInState(overrides = {}) {
  _signInState = { ..._signInState, ...overrides }
}

vi.mock('@clerk/react', () => ({
  useAuth: () => ({
    isSignedIn: _clerkState.isSignedIn,
    isLoaded: _clerkState.isLoaded,
    userId: _clerkState.isSignedIn ? _clerkState.userId : null,
    getToken: async () => _clerkState.isSignedIn ? 'test_token_123' : null,
  }),
  useUser: () => ({
    user: _clerkState.isSignedIn ? {
      id: _clerkState.userId,
      primaryEmailAddress: { emailAddress: 'test@cronos.pt' },
      fullName: 'Test User',
    } : null,
    isLoaded: _clerkState.isLoaded,
  }),
  useOrganization: () => ({
    organization: _clerkState.orgId
      ? { id: _clerkState.orgId, name: _clerkState.orgName, slug: 'test-org' }
      : null,
    membership: _clerkState.role ? {
      role: _clerkState.role,
      publicMetadata: { teacher_id: _clerkState.teacherId },
    } : null,
    isLoaded: _clerkState.isLoaded,
  }),
  useOrganizationList: () => ({
    isLoaded: _clerkState.isLoaded,
    createOrganization: vi.fn().mockResolvedValue({ id: 'org_created' }),
    setActive: vi.fn().mockResolvedValue(undefined),
    userMemberships: {
      data: _clerkState.memberships || (_clerkState.orgId ? [{
        organization: {
          id: _clerkState.orgId,
          name: _clerkState.orgName,
        },
      }] : []),
    },
  }),
  useClerk: () => ({
    openUserProfile: vi.fn(),
    openOrganizationProfile: vi.fn(),
    signOut: vi.fn(),
  }),
  useSignIn: () => _signInState,
  ClerkProvider: ({ children }) => children,
  SignIn: () => null,
  SignUp: () => null,
  CreateOrganization: () => null,
  Show: ({ children, when, fallback }) => {
    if (when === 'signed-out') return _clerkState.isSignedIn ? (fallback || null) : children
    return children
  },
  RedirectToSignIn: () => null,
  UserButton: () => null,
  OrganizationSwitcher: () => null,
  Protect: ({ children, role, condition, fallback }) => {
    if (role && _clerkState.role !== role) return fallback || null
    if (condition && !condition({ role: _clerkState.role })) return fallback || null
    return children
  },
}))
