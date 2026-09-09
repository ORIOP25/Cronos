import { useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { CSpinner } from '@coreui/react'
import { useQueryClient } from '@tanstack/react-query'
import {
  OrganizationSwitcher,
  RedirectToSignIn,
  useAuth,
  useClerk,
  useOrganization,
  useOrganizationList,
} from '@clerk/react'
import { CURRENT_LEGAL_VERSIONS } from './features/legal/data'
import { useOnboardingCompletion } from './features/onboarding/useOnboardingCompletion'
import { recoverOrganizationSession } from './features/members/recoverOrganizationSession'
import apiClient from './apiClient'
import {
  canAccessTeacherRoutes,
  getDefaultRouteForMember,
  hasMemberCapability,
} from './roleAccess'

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
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <PageLoader />
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
  return (
    <div className="container py-3 text-center" role="alert">
      <p className="mb-2">Não foi possível concluir a configuração da sessão.</p>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => void retry()}>
        Tentar novamente
      </button>
    </div>
  )
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
  const queryClient = useQueryClient()
  const organizationState = useOrganization()
  const list = useOrganizationList({ userMemberships: { infinite: true } })
  const onboarding = useOnboardingCompletion(organizationState)
  return {
    ...auth,
    organization: organizationState.organization,
    organizationMembership: organizationState.membership,
    orgLoaded: organizationState.isLoaded,
    listLoaded: list.isLoaded,
    memberships: list.userMemberships?.data || [],
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

function MemberGate({ children, capability, requireTeacherId = false, redirectToDefault = false, allowUncompletedFoundation = false }) {
  const state = useOrganizationGuardState()
  const { data: member, isLoading: memberLoading, isError, error, refetch } = state.member
  if (!state.isLoaded || !state.orgLoaded || !state.listLoaded) return <PageLoader />
  if (!state.isSignedIn) return <RedirectToCurrentPageSignIn />
  if (!state.organization) return <OrganizationRequired memberships={state.memberships} />
  if (!state.userLoaded) return <PageLoader />
  if (memberLoading || state.isCompleting || (state.bootstrapRequired && !state.error)) return <PageLoader />
  if (state.error) return <OnboardingFailure retry={state.retry} />
  if (isError) return <MemberQueryFailure error={error} recoverSession={state.recoverSession} refetch={refetch} signOut={state.signOut} />
  if (state.legal.isLoading) return <PageLoader />
  if (state.legal.isError) return <OnboardingFailure retry={state.retry} />
  if (state.legal.data?.requires_acceptance) {
    if (state.needsManualLegalAcceptance && state.isAdmin) {
      return <LegalReacceptanceDialog legal={state.legal} acceptance={state.acceptance} />
    }
    return <LegalAdminRequired />
  }
  if (redirectToDefault) return <Navigate to={getDefaultRouteForMember(member)} replace />

  // Foundation gate: incomplete organizations have no operational routes.
  const isOrgAdmin = hasMemberCapability(member, 'admin')
  if (!allowUncompletedFoundation && member && member.foundation_status !== 'COMPLETED') {
    return <Navigate to={isOrgAdmin ? '/foundation' : '/foundation/waiting'} replace />
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
  return <MemberGate capability="admin" allowUncompletedFoundation>{children}</MemberGate>
}

export function RequireTeacher({ children }) {
  return <MemberGate capability="teacher" requireTeacherId>{children}</MemberGate>
}

export function SignedInRedirect() {
  return <MemberGate redirectToDefault />
}
