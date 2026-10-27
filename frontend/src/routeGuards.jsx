import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import { useIsMutating, useQueryClient } from '@tanstack/react-query'
import {
  OrganizationSwitcher,
  RedirectToTasks,
  RedirectToSignIn,
  useAuth,
  useClerk,
  useOrganization,
  useOrganizationList,
  useSession,
} from '@clerk/react'
import { CURRENT_LEGAL_VERSIONS } from './features/legal/data'
import { FOUNDATION_COMPLETE_ROOT } from './features/foundation/foundationData'
import { orgQueryKey } from './features/queryKeys'
import { useOnboardingCompletion } from './features/onboarding/useOnboardingCompletion'
import { recoverOrganizationSession } from './features/members/recoverOrganizationSession'
import apiClient from './apiClient'
import {
  canAccessTeacherRoutes,
  getDefaultRouteForMember,
  getFoundationLandingRoute,
  getMemberRoute,
  hasMemberCapability,
  isFoundationComplete,
  ROUTE_DASHBOARD,
  ROUTE_FOUNDATION_WAITING,
  ROUTE_SCHOOL_CONFIG,
} from './roleAccess'
import FailureState from './components/FailureState'
import { getApiErrorPresentation } from './utils/apiErrors'

export const PageLoader = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '40vh' }}>
    <CSpinner color="primary" />
  </div>
)

function RedirectToCurrentPageSignIn() {
  const location = useLocation()
  return <RedirectToSignIn redirectUrl={`${location.pathname}${location.search}${location.hash}`} />
}

export function RequireAuth({ children }) {
  const { isSignedIn, isLoaded } = useAuth({ treatPendingAsSignedOut: false })
  const { session, isLoaded: sessionLoaded } = useSession()
  if (!isLoaded || !sessionLoaded) return <PageLoader />
  if (session?.currentTask) return <RedirectToTasks />
  if (!isSignedIn) return <RedirectToCurrentPageSignIn />
  return children ?? <Outlet />
}

function OrganizationRequired({ memberships }) {
  return (
    <div className="container py-5 text-center" data-testid="organization-selector">
      <h1 className="h4">Selecione uma organização</h1>
      <p>{memberships?.length ? 'Escolha a escola onde pretende trabalhar.' : 'A sua sessão ainda não tem uma escola ativa.'}</p>
      <OrganizationSwitcher hidePersonal />
    </div>
  )
}

function OnboardingFailure({ retry }) {
  return <FailureState presentation={{ ...getApiErrorPresentation({}, 'organization'), message: 'Não foi possível preparar o seu acesso. Tente novamente.' }} onRetry={() => void retry()} variant="inline" />
}

function LegalAdminRequired() {
  return (
    <div className="container py-3 text-center" role="alert">
      <p className="mb-2">Um administrador da organização deve aceitar os documentos legais antes de continuar.</p>
      <OrganizationSwitcher hidePersonal />
    </div>
  )
}

function LegalReacceptanceDialog({ legal, acceptance }) {
  const [confirmed, setConfirmed] = useState(false)
  const status = legal.data || {}
  const isPending = acceptance.isPending
  const accept = async () => {
    try {
      await acceptance.mutateAsync({
        acceptance_confirmed: true,
        terms_version: status.terms_version || CURRENT_LEGAL_VERSIONS.terms_version,
        dpa_version: status.dpa_version || CURRENT_LEGAL_VERSIONS.dpa_version,
        privacy_version: status.privacy_version || CURRENT_LEGAL_VERSIONS.privacy_version,
      })
    } catch {
      // The mutation state renders a compact retryable error in this dialog.
    }
  }

  return (
    <div className="container py-4" role="dialog" aria-labelledby="legal-reacceptance-title">
      <div className="mx-auto" style={{ maxWidth: '38rem' }}>
        <h1 id="legal-reacceptance-title" className="h4">Atualização dos documentos legais</h1>
        <p>Reveja os documentos atuais e confirme a aceitação da organização.</p>
        <p className="mb-2">
          <a href="/termos">Termos de Serviço</a>{' · '}
          <a href="/dpa">Acordo de Tratamento de Dados</a>{' · '}
          <a href="/privacidade">Política de Privacidade</a>
        </p>
        <label className="d-flex gap-2 align-items-start mb-3">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>Confirmo a aceitação dos documentos legais atuais pela organização.</span>
        </label>
        {acceptance.error && <p className="text-danger small" role="alert">Não foi possível registar a aceitação.</p>}
        <button type="button" className="btn btn-primary" disabled={!confirmed || isPending} onClick={() => void accept()}>
          {isPending ? 'A guardar…' : 'Confirmar e continuar'}
        </button>
      </div>
    </div>
  )
}

function MemberQueryFailure({ error, recoverSession, refetch, signOut }) {
  const status = error?.response?.status
  const presentation = {
    ...getApiErrorPresentation(error, 'organization'),
    message: status === 401
      ? 'A sua sessão precisa de ser renovada. Entre novamente para continuar.'
      : status === 403
        ? 'A sua conta não tem acesso a esta organização.'
        : 'Não foi possível confirmar o acesso. Verifique a ligação e tente novamente.',
  }
  return (
    <div className="container py-3">
      <FailureState
        presentation={presentation}
        onRetry={status === 403 ? undefined : status === 401 ? () => void recoverSession() : () => void refetch()}
        retryLabel={status === 401 ? 'Atualizar sessão' : 'Tentar novamente'}
        secondaryAction={status === 401 ? (
          <button type="button" className="btn-zen btn-zen-ghost" onClick={() => void signOut({ redirectUrl: '/login' })}>
            Terminar sessão
          </button>
        ) : null}
        variant="inline"
      />
      <div className="mt-3"><OrganizationSwitcher hidePersonal /></div>
    </div>
  )
}

function useOrganizationGuardState() {
  const auth = useAuth({ treatPendingAsSignedOut: false })
  const sessionState = useSession()
  const clerk = useClerk()
  const queryClient = useQueryClient()
  const organizationState = useOrganization()
  const list = useOrganizationList({ userMemberships: { infinite: true } })
  const onboarding = useOnboardingCompletion(organizationState)
  const autoActivationAttempted = useRef(false)
  const [activationPending, setActivationPending] = useState(false)
  const [activationError, setActivationError] = useState(null)
  const membershipData = list.userMemberships?.data
  const setActive = list.setActive
  const memberships = useMemo(() => membershipData || [], [membershipData])
  const soleOrganizationId = useMemo(
    () => memberships.length === 1 ? memberships[0]?.organization?.id : null,
    [memberships],
  )
  useEffect(() => {
    if (!list.isLoaded || !organizationState.isLoaded || organizationState.organization || !soleOrganizationId || autoActivationAttempted.current) return
    autoActivationAttempted.current = true
    setActivationPending(true)
    Promise.resolve(setActive({ organization: soleOrganizationId }))
      .then(() => setActivationPending(false))
      .catch((error) => {
        setActivationError(error)
        setActivationPending(false)
      })
  }, [setActive, list.isLoaded, organizationState.isLoaded, organizationState.organization, soleOrganizationId])
  return {
    ...auth,
    session: sessionState.session,
    sessionLoaded: sessionState.isLoaded,
    organization: organizationState.organization,
    organizationMembership: organizationState.membership,
    orgLoaded: organizationState.isLoaded,
    listLoaded: list.isLoaded,
    memberships,
    activationPending,
    activationError,
    ...onboarding,
    recoverSession: async () => {
      const organizationId = organizationState.organization?.id
      const currentMember = await recoverOrganizationSession({
        getToken: auth.getToken,
        organizationId,
        requestMember: (token) => apiClient.get('/members/me', {
          headers: { Authorization: `Bearer ${token}` },
        }),
      })
      queryClient.setQueryData(['current-member', organizationId], currentMember)
    },
    signOut: clerk.signOut,
  }
}

function MemberGate({ children, capability, requireTeacherId = false, redirectToMemberRoute = false, allowUncompletedFoundation = false, foundationWizard = false }) {
  const state = useOrganizationGuardState()
  const foundationCompletionPending = useIsMutating({
    mutationKey: orgQueryKey(FOUNDATION_COMPLETE_ROOT, state.organization?.id),
  }) > 0
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.sessionLoaded) return <PageLoader />
  if (state.session?.currentTask) return <RedirectToTasks />
  if (!state.isSignedIn) return <RedirectToCurrentPageSignIn />
  if (!state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (state.activationPending && !state.organization) return <PageLoader />
  if (state.activationError) return <FailureState presentation={getApiErrorPresentation(state.activationError, 'organization')} onRetry={() => globalThis.location.reload()} />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (!state.userLoaded) return <PageLoader />
  if (memberLoading || state.isCompleting || (state.bootstrapRequired && !state.error)) return <PageLoader />
  if (state.error) return <OnboardingFailure retry={state.retry} />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  if (!member) return <PageLoader />
  if (state.legal.isLoading) return <PageLoader />
  if (state.legal.isError) return <OnboardingFailure retry={state.retry} />
  if (state.legal.data?.requires_acceptance) {
    if (state.needsManualLegalAcceptance && state.isAdmin) {
      return <LegalReacceptanceDialog legal={state.legal} acceptance={state.acceptance} />
    }
    return <LegalAdminRequired />
  }
  // The incomplete organization still owns the destination: a founder opens the
  // wizard and every other member waits there instead of an operational route.
  if (redirectToMemberRoute) return <Navigate to={getMemberRoute(member)} replace />

  // Foundation wizard: only the founder of an incomplete organization runs it.
  // Keep an activation in progress on its dashboard destination while caches reconcile.
  // Revisiting the wizard after completion opens school configuration.
  if (foundationWizard) {
    if (isFoundationComplete(member)) {
      return hasMemberCapability(member, 'admin')
        ? <Navigate to={foundationCompletionPending ? ROUTE_DASHBOARD : ROUTE_SCHOOL_CONFIG} replace />
        : <Navigate to={getDefaultRouteForMember(member)} replace />
    }
    const canRunWizard = hasMemberCapability(member, 'admin') && member.can_manage_foundation === true
    return canRunWizard
      ? children ?? <Outlet />
      : <Navigate to={ROUTE_FOUNDATION_WAITING} replace />
  }

  // Foundation gate: incomplete organizations have no operational routes.
  if (!allowUncompletedFoundation && !isFoundationComplete(member)) {
    return <Navigate to={getFoundationLandingRoute(member)} replace />
  }

  const allowed = requireTeacherId
    ? canAccessTeacherRoutes(member)
    : hasMemberCapability(member, capability)
  if (!allowed) return <Navigate to={getDefaultRouteForMember(member)} replace />
  return children ?? <Outlet />
}

export function RequireAdmin({ children }) {
  return <MemberGate capability="admin">{children}</MemberGate>
}

export function RequireFoundationAdmin({ children }) {
  return <MemberGate foundationWizard>{children}</MemberGate>
}

export function RequireGuide({ children }) {
  return <MemberGate capability="admin" allowUncompletedFoundation>{children}</MemberGate>
}

export function RequireTeacher({ children }) {
  return <MemberGate capability="teacher" requireTeacherId>{children}</MemberGate>
}

export function SignedInRedirect() {
  return <MemberGate redirectToMemberRoute />
}
