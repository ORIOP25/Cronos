import React, { Suspense } from 'react'
import { Navigate } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import { RedirectToSignIn, useAuth, useOrganization } from '@clerk/react'
import { getDefaultRouteForRole, getForbiddenRedirectRoute, USER_ROLE_ADMIN, USER_ROLE_TEACHER } from './roleAccess'

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

export function RequireAdmin({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== USER_ROLE_ADMIN) return <Navigate to={getForbiddenRedirectRoute(membership?.role)} />
  return children
}

export function RequireTeacher({ children }) {
  const { isSignedIn, isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <PageLoader />
  if (!isSignedIn) return <RedirectToSignIn />
  if (membership?.role !== USER_ROLE_TEACHER) return <Navigate to={getForbiddenRedirectRoute(membership?.role)} />
  return children
}

export function SignedInRedirect() {
  const { isLoaded } = useAuth()
  const { membership, isLoaded: orgLoaded } = useOrganization()
  if (!isLoaded || !orgLoaded) return <PageLoader />
  return <Navigate to={getDefaultRouteForRole(membership?.role)} replace />
}
