import '@testing-library/jest-dom'
import { vi } from 'vitest'

vi.mock('@clerk/react', () => ({
  useAuth: () => ({
    isSignedIn: true,
    isLoaded: true,
    userId: 'user_test_123',
    getToken: async () => 'test_token_123',
  }),
  useUser: () => ({
    user: {
      id: 'user_test_123',
      primaryEmailAddress: { emailAddress: 'test@example.com' },
      fullName: 'Test User',
      publicMetadata: { teacherId: 1, role: 'admin' },
    },
    isLoaded: true,
  }),
  useOrganization: () => ({
    organization: { id: 1, name: 'Test Org' },
    membership: { role: 'org:admin' },
    isLoaded: true,
  }),
  ClerkProvider: ({ children }) => children,
  SignIn: () => null,
  SignUp: () => null,
  UserButton: () => null,
  OrganizationSwitcher: () => null,
  CreateOrganization: () => null,
  Show: ({ children }) => children,
  RedirectToSignIn: () => null,
}))
