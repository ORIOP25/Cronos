import React, { Suspense } from 'react'
import { Navigate } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import { RedirectToSignIn, useAuth, useOrganization } from '@clerk/react'
import { useCurrentMember } from './hooks/useSchoolData'
import { getDefaultRouteForMember, getForbiddenRedirectRoute, ROUTE_CREATE_ORG } from './roleAccess'

export const PageLoader = () => (
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

export function RequireAdmin({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { organization, isLoaded: orgLoaded } = useOrganization()
  const { data: member, isLoading: memberLoading } = useCurrentMember({ enabled: Boolean(organization) })
  if (!isLoaded || !orgLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (!organization) return <Navigate to={ROUTE_CREATE_ORG} replace />
  if (memberLoading) return <PageLoader />
  if (!hasCapability(member, 'admin')) return <Navigate to={getForbiddenRedirectRoute(member)} replace />
  return children
}

export function RequireTeacher({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { organization, isLoaded: orgLoaded } = useOrganization()
  const { data: member, isLoading: memberLoading } = useCurrentMember({ enabled: Boolean(organization) })
  if (!isLoaded || !orgLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (!organization) return <Navigate to={ROUTE_CREATE_ORG} replace />
  if (memberLoading) return <PageLoader />
  if (!hasCapability(member, 'teacher') || !member?.teacher_id) {
    return <Navigate to={getForbiddenRedirectRoute(member)} replace />
  }
  return children
}

export function SignedInRedirect() {
  const { isLoaded } = useAuth()
  const { organization, isLoaded: orgLoaded } = useOrganization()
  const { data: member, isLoading: memberLoading } = useCurrentMember({ enabled: Boolean(organization) })
  if (!isLoaded || !orgLoaded) return <PageLoader />
  if (!organization) return <Navigate to={ROUTE_CREATE_ORG} replace />
  if (memberLoading) return <PageLoader />
  return <Navigate to={getDefaultRouteForMember(member)} replace />
}
