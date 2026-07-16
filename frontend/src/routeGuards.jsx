import { Navigate, Outlet } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import {
  OrganizationSwitcher,
  RedirectToSignIn,
  useAuth,
  useClerk,
  useOrganization,
  useOrganizationList,
} from '@clerk/react'
import { useCurrentMember } from './features/members/data'
import {
  ROUTE_CREATE_ORG,
  canAccessTeacherRoutes,
  getDefaultRouteForMember,
  hasMemberCapability,
} from './roleAccess'

export const PageLoader = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '40vh' }}>
    <CSpinner color="primary" />
  </div>
)

export function RequireAuth({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  return children ?? <Outlet />
}

function OrganizationRequired({ memberships }) {
  if (!memberships?.length) return <Navigate to={ROUTE_CREATE_ORG} replace />
  return (
    <div className="container py-5 text-center" data-testid="organization-selector">
      <h1 className="h4">Selecione uma organização</h1>
      <p>A sua sessão não tem uma organização ativa.</p>
      <OrganizationSwitcher hidePersonal />
    </div>
  )
}

function MemberQueryFailure({ error, recoverSession, refetch, signOut }) {
  const status = error?.response?.status
  const message = status === 401
    ? 'A sessão da organização precisa de ser atualizada.'
    : status === 403
      ? 'A sua conta não tem acesso a esta organização.'
      : 'Não foi possível confirmar o acesso. Verifique a ligação e tente novamente.'
  return (
    <div className="container py-5 text-center" role="alert">
      <p>{message}</p>
      {status === 401 && (
        <>
          <button type="button" className="btn btn-primary" onClick={() => void recoverSession()}>Atualizar sessão</button>
          <button type="button" className="btn btn-link" onClick={() => void signOut({ redirectUrl: '/login' })}>Terminar sessão</button>
        </>
      )}
      {status !== 401 && status !== 403 && (
        <button type="button" className="btn btn-primary" onClick={() => void refetch()}>Tentar novamente</button>
      )}
      <div className="mt-3"><OrganizationSwitcher hidePersonal /></div>
    </div>
  )
}

function useOrganizationGuardState() {
  const auth = useAuth()
  const clerk = useClerk()
  const organizationState = useOrganization()
  const list = useOrganizationList({ userMemberships: { infinite: true } })
  const member = useCurrentMember({ enabled: Boolean(organizationState.organization) })
  return {
    ...auth,
    organization: organizationState.organization,
    orgLoaded: organizationState.isLoaded,
    listLoaded: list.isLoaded,
    memberships: list.userMemberships?.data || [],
    member,
    recoverSession: async () => {
      await auth.getToken({
        organizationId: organizationState.organization?.id,
        skipCache: true,
      })
      await member.refetch()
    },
    signOut: clerk.signOut,
  }
}

function MemberGate({ children, capability, requireTeacherId = false, redirectToDefault = false }) {
  const state = useOrganizationGuardState()
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (!state.isSignedIn) return <RedirectToSignIn />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (memberLoading) return <PageLoader />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  if (redirectToDefault) return <Navigate to={getDefaultRouteForMember(member)} replace />
  const allowed = requireTeacherId
    ? canAccessTeacherRoutes(member)
    : hasMemberCapability(member, capability)
  if (!allowed) return <Navigate to={getDefaultRouteForMember(member)} replace />
  return children ?? <Outlet />
}

export function RequireAdmin({ children }) {
  return <MemberGate capability="admin">{children}</MemberGate>
}

export function RequireTeacher({ children }) {
  return <MemberGate capability="teacher" requireTeacherId>{children}</MemberGate>
}

export function SignedInRedirect() {
  return <MemberGate redirectToDefault />
}
