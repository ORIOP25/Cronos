import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders, renderWithRouter } from './testUtils'
import { setClerkState, resetClerkState } from './setup'
import {
  RequireAdmin,
  RequireAuth,
  RequireTeacher,
  SignedInRedirect,
} from '../routeGuards'
import { recoverOrganizationSession } from '../features/members/recoverOrganizationSession'

const memberState = vi.hoisted(() => ({
  value: {
    access_status: 'active',
    lifecycle_status: 'active',
    capabilities: ['admin'],
    default_mode: 'admin',
    teacher_id: null,
    foundation_status: 'COMPLETED',
  },
  loading: false,
  error: null,
}))

const legalState = vi.hoisted(() => ({
  value: {
    accepted: true,
    requires_acceptance: false,
    terms_version: '2026-01',
    dpa_version: '2026-01',
    privacy_version: '2026-01',
  },
  loading: false,
  error: null,
  refetch: vi.fn(),
}))

const orgAdminState = vi.hoisted(() => ({ value: true }))
const onboardingErrorState = vi.hoisted(() => ({ value: null, retry: vi.fn() }))

vi.mock('../features/onboarding/useOnboardingCompletion', () => ({
  useOnboardingCompletion: () => ({
    member: {
      data: memberState.value,
      isLoading: memberState.loading,
      isError: Boolean(memberState.error),
      error: memberState.error,
      refetch: vi.fn(),
    },
    legal: {
      data: legalState.value,
      isLoading: legalState.loading,
      isError: Boolean(legalState.error),
      error: legalState.error,
      refetch: legalState.refetch,
    },
    acceptance: { isPending: false, error: null, mutateAsync: vi.fn(), reset: vi.fn() },
    userLoaded: true,
    isAdmin: orgAdminState.value,
    bootstrapRequired: Boolean(orgAdminState.value && memberState.error?.response?.status === 403),
    isCompleting: false,
    error: onboardingErrorState.value,
    retry: onboardingErrorState.retry,
    needsManualLegalAcceptance: Boolean(legalState.value?.requires_acceptance),
  }),
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({
    data: memberState.value,
    isLoading: memberState.loading,
    isError: Boolean(memberState.error),
    error: memberState.error,
    refetch: vi.fn(),
  }),
}))

vi.mock('../features/legal/data', async (importOriginal) => ({
  ...(await importOriginal()),
  useLegalStatus: () => ({
    data: legalState.value,
    isLoading: legalState.loading,
    isError: Boolean(legalState.error),
    error: legalState.error,
    refetch: legalState.refetch,
  }),
}))

function renderGuard(ui, initialEntries = ['/protected']) {
  return renderWithRouter(
    <Routes>
      <Route path="/protected" element={ui} />
      <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
      <Route path="/my-availability" element={<div data-testid="teacher-route">Teacher</div>} />
      <Route path="/foundation" element={<div data-testid="foundation-route">Foundation</div>} />
      <Route path="/login" element={<div data-testid="login-route">Login</div>} />
    </Routes>,
    { initialEntries },
  )
}

function renderRedirect() {
  return renderWithRouter(
    <Routes>
      <Route path="/" element={<SignedInRedirect />} />
      <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
      <Route path="/my-availability" element={<div data-testid="teacher-route">Teacher</div>} />
      <Route path="/foundation" element={<div data-testid="foundation-route">Foundation</div>} />
    </Routes>,
  )
}

describe('RequireAuth', () => {
  beforeEach(() => resetClerkState())

  it('renders children when signed in', () => {
    setClerkState({ isSignedIn: true, isLoaded: true })
    renderGuard(<RequireAuth><div data-testid="child">Content</div></RequireAuth>)
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderGuard(<RequireAuth><div>Content</div></RequireAuth>)
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
    expect(screen.queryByTestId('redirect-to-sign-in')).toBeNull()
  })

  it('redirects to sign-in when signed out', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderGuard(<RequireAuth><div>Content</div></RequireAuth>)
    expect(screen.queryByText('Content')).toBeNull()
    expect(screen.getByTestId('redirect-to-sign-in')).toBeInTheDocument()
  })

  it('redirects when an active session is lost', () => {
    const view = renderWithProviders(
      <MemoryRouter initialEntries={['/protected']}>
        <RequireAuth><div data-testid="protected-content">Content</div></RequireAuth>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('protected-content')).toBeInTheDocument()

    setClerkState({ isSignedIn: false })
    view.rerender(
      <MemoryRouter initialEntries={['/protected']}>
        <RequireAuth><div data-testid="protected-content">Content</div></RequireAuth>
      </MemoryRouter>,
    )

    expect(screen.queryByTestId('protected-content')).toBeNull()
    expect(screen.getByTestId('redirect-to-sign-in')).toBeInTheDocument()
  })

  it('passes the current path, query and fragment to the native sign-in redirect', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderGuard(<RequireAuth><div>Content</div></RequireAuth>, ['/protected?tab=week#availability'])

    expect(screen.getByTestId('redirect-to-sign-in')).toHaveAttribute(
      'data-redirect-url',
      '/protected?tab=week#availability',
    )
  })
})

describe('recoverOrganizationSession', () => {
  it('uses the freshly minted organization token for the member request', async () => {
    const getToken = vi.fn().mockResolvedValue('fresh-org-token')
    const requestMember = vi.fn().mockResolvedValue({ id: 1 })

    await expect(recoverOrganizationSession({
      getToken,
      organizationId: 'org_123',
      requestMember,
    })).resolves.toEqual({ id: 1 })

    expect(getToken).toHaveBeenCalledWith({ organizationId: 'org_123', skipCache: true })
    expect(requestMember).toHaveBeenCalledWith('fresh-org-token')
  })
})

describe('RequireAdmin', () => {
  beforeEach(() => {
    resetClerkState()
    orgAdminState.value = true
    onboardingErrorState.value = null
    onboardingErrorState.retry.mockReset()
    memberState.loading = false
    memberState.error = null
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      teacher_id: null,
      foundation_status: 'COMPLETED',
    }
    legalState.value = {
      accepted: true,
      requires_acceptance: false,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    }
    legalState.loading = false
    legalState.error = null
    legalState.refetch.mockReset()
  })

  it('allows active local admin capability', () => {
    renderGuard(<RequireAdmin><div data-testid="admin-content">Admin</div></RequireAdmin>)
    expect(screen.getByTestId('admin-content')).toBeInTheDocument()
  })

  it('blocks teacher-only member and redirects to teacher default route', () => {
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      default_mode: 'teacher',
      teacher_id: 10,
      foundation_status: 'COMPLETED',
    }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.queryByText('Admin')).toBeNull()
    expect(screen.getByTestId('teacher-route')).toBeInTheDocument()
  })

  it('redirects unauthenticated to sign-in', () => {
    setClerkState({ isSignedIn: false, isLoaded: true })
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.queryByText('Admin')).toBeNull()
    expect(screen.getByTestId('redirect-to-sign-in')).toBeInTheDocument()
  })
})

describe('RequireTeacher', () => {
  beforeEach(() => {
    resetClerkState()
    orgAdminState.value = true
    onboardingErrorState.value = null
    onboardingErrorState.retry.mockReset()
    memberState.loading = false
    memberState.error = null
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      default_mode: 'teacher',
      teacher_id: 10,
      foundation_status: 'COMPLETED',
    }
  })

  it('shows session recovery for a member-query 401 without redirecting to create org', () => {
    memberState.error = { response: { status: 401 } }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByText(/sessão da organização precisa/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Atualizar sessão/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Terminar sessão/i })).toBeInTheDocument()
    expect(screen.queryByText('Admin')).toBeNull()
  })

  it('keeps an organization admin in the normal loading state while bootstrap runs', () => {
    memberState.error = { response: { status: 403 } }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
  })

  it('shows access denied for a non-admin member-query 403', () => {
    setClerkState({ role: 'org:member' })
    orgAdminState.value = false
    memberState.error = { response: { status: 403 } }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByText(/não tem acesso a esta organização/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Tentar novamente/i })).toBeNull()
  })

  it('shows a retry panel for a member-query 5xx', () => {
    memberState.error = { response: { status: 503 } }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByText(/Não foi possível confirmar o acesso/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tentar novamente/i })).toBeInTheDocument()
  })

  it('shows organization selection when memberships exist but none is active', () => {
    setClerkState({
      orgId: null,
      memberships: [{ organization: { id: 'org_other', name: 'Outra escola' } }],
    })
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByTestId('organization-selector')).toBeInTheDocument()
  })

  it('allows active local teacher capability with teacher profile', () => {
    renderGuard(<RequireTeacher><div data-testid="teacher-content">Teacher</div></RequireTeacher>)
    expect(screen.getByTestId('teacher-content')).toBeInTheDocument()
  })

  it('allows mixed admin plus teacher capability even when Clerk role is org:admin', () => {
    setClerkState({ role: 'org:admin' })
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin', 'teacher'],
      default_mode: 'admin',
      teacher_id: 10,
      foundation_status: 'COMPLETED',
    }
    renderGuard(<RequireTeacher><div data-testid="teacher-content">Teacher</div></RequireTeacher>)
    expect(screen.getByTestId('teacher-content')).toBeInTheDocument()
  })

  it('blocks admin-only member and redirects to admin default route', () => {
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      teacher_id: null,
      foundation_status: 'COMPLETED',
    }
    renderGuard(<RequireTeacher><div>Teacher</div></RequireTeacher>)
    expect(screen.queryByText('Teacher')).toBeNull()
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })
})

describe('SignedInRedirect', () => {
  beforeEach(() => {
    resetClerkState()
    orgAdminState.value = true
    onboardingErrorState.value = null
    onboardingErrorState.retry.mockReset()
    memberState.loading = false
    memberState.error = null
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      teacher_id: null,
      foundation_status: 'COMPLETED',
    }
    legalState.value = {
      accepted: true,
      requires_acceptance: false,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    }
    legalState.loading = false
    legalState.error = null
  })

  it('shows a compact retry alert when background onboarding fails', () => {
    onboardingErrorState.value = new Error('bootstrap failed')
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>)
    expect(screen.getByText(/não foi possível concluir a configuração/i)).toBeInTheDocument()
    screen.getByRole('button', { name: /tentar novamente/i }).click()
    expect(onboardingErrorState.retry).toHaveBeenCalledTimes(1)
  })

  it('redirects admin to /dashboard', () => {
    renderRedirect()
    expect(screen.getByTestId('dashboard-route')).toBeInTheDocument()
  })

  it('redirects teacher to /my-availability', () => {
    memberState.value = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      default_mode: 'teacher',
      teacher_id: 10,
      foundation_status: 'COMPLETED',
    }
    renderRedirect()
    expect(screen.getByTestId('teacher-route')).toBeInTheDocument()
  })

  it('redirects missing member to /foundation', () => {
    memberState.value = null
    renderRedirect()
    expect(screen.getByTestId('foundation-route')).toBeInTheDocument()
  })

  it('keeps missing legal acceptance inside the guarded flow', () => {
    legalState.value = {
      accepted: false,
      requires_acceptance: true,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    }
    renderGuard(<RequireAdmin><div>Admin</div></RequireAdmin>, ['/protected?tab=week#availability'])
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /atualização dos documentos legais/i })).toBeInTheDocument()
  })

  it('shows loader when Clerk not loaded', () => {
    setClerkState({ isLoaded: false })
    renderRedirect()
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
  })
})
