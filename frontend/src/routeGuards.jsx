import React, { Suspense } from 'react'
import { Navigate } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import {
  OrganizationSwitcher,
  RedirectToSignIn,
  useAuth,
  useClerk,
  useOrganization,
  useOrganizationList,
} from '@clerk/react'
import { useCurrentMember } from './hooks/useSchoolData'
import { getDefaultRouteForMember, getForbiddenRedirectRoute, ROUTE_CREATE_ORG } from './roleAccess'

const PageLoader = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '40vh' }}>
    <CSpinner color="primary" />
  </div>
)

export function LazyPage({ children }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}

export function RequireAuth({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  return children
}

function hasCapability(member, capability) {
  return (
    member?.access_status === 'active'
    && member?.lifecycle_status === 'active'
    && member?.capabilities?.includes(capability)
  )
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

export function RequireAdmin({ children }) {
  const state = useOrganizationGuardState()
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (!state.isSignedIn) return <RedirectToSignIn />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (memberLoading) return <PageLoader />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  if (!hasCapability(member, 'admin')) return <Navigate to={getForbiddenRedirectRoute(member)} replace />
  return children
}

export function RequireTeacher({ children }) {
  const state = useOrganizationGuardState()
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (!state.isSignedIn) return <RedirectToSignIn />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (memberLoading) return <PageLoader />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  if (!hasCapability(member, 'teacher') || !member?.teacher_id) {
    return <Navigate to={getForbiddenRedirectRoute(member)} replace />
  }
  return children
}

export function SignedInRedirect() {
  const state = useOrganizationGuardState()
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (!state.isSignedIn) return <RedirectToSignIn />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (memberLoading) return <PageLoader />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  return <Navigate to={getDefaultRouteForMember(member)} replace />
}
