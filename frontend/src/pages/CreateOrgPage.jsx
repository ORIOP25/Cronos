import { useCallback, useEffect, useRef, useState } from 'react'
import { OrganizationSwitcher, useClerk, useOrganization } from '@clerk/react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import BrandPanel from '../components/auth/BrandPanel'
import { useAcceptLegalDocuments, useLegalStatus } from '../features/legal/data'
import { useCurrentMember } from '../features/members/data'
import { useCreateActiveOrganization } from '../features/organization/useCreateActiveOrganization'
import { getDefaultRouteForMember, hasMemberCapability } from '../roleAccess'
import { getApiErrorMessage } from '../utils/apiErrors'
import {
  BRAND_STATS_CREATEORG,
  BRAND_TAGLINE_CREATEORG,
} from '../utils/authDesign'

const LEGAL_CONFIRMATION_TEXT = 'Confirmo que tenho poderes para vincular a organização, aceito os Termos de Serviço e o Acordo de Tratamento de Dados (DPA), e declaro que li a Política de Privacidade.'

function safeInternalReturnPath(value) {
  return typeof value === 'string'
    && value.startsWith('/')
    && !value.startsWith('//')
    && !value.includes('://')
    ? value
    : ''
}

export default function CreateOrgPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const clerk = useClerk()
  const { organization, membership } = useOrganization()
  const member = useCurrentMember({ enabled: Boolean(organization?.id) })
  const legal = useLegalStatus({ enabled: Boolean(organization?.id && member.data) })
  const acceptance = useAcceptLegalDocuments()
  const { bootstrapActiveOrganization, isPending: bootstrapPending, error: bootstrapError } = useCreateActiveOrganization()
  const [actionError, setActionError] = useState('')
  const attemptedBootstrapOrganizationId = useRef(null)
  const navigatedOrganizationId = useRef(null)
  const returnPath = safeInternalReturnPath(location.state?.from)
  const clerkAdmin = ['admin', 'org:admin'].includes(membership?.role)
  const isAdmin = clerkAdmin || hasMemberCapability(member.data, 'admin')

  useEffect(() => {
    attemptedBootstrapOrganizationId.current = null
    navigatedOrganizationId.current = null
  }, [organization?.id])

  const startBootstrap = useCallback(() => {
    if (!organization?.id) return
    attemptedBootstrapOrganizationId.current = organization.id
    setActionError('')
    void bootstrapActiveOrganization().catch((failure) => {
      setActionError(getApiErrorMessage(failure, failure?.message || 'Não foi possível preparar a organização.'))
    })
  }, [bootstrapActiveOrganization, organization])

  useEffect(() => {
    if (!organization?.id || !isAdmin || !member.isError) return
    if (attemptedBootstrapOrganizationId.current === organization.id) return
    attemptedBootstrapOrganizationId.current = organization.id
    void bootstrapActiveOrganization().catch((failure) => {
      setActionError(getApiErrorMessage(failure, failure?.message || 'Não foi possível preparar a organização.'))
    })
  }, [bootstrapActiveOrganization, isAdmin, member.isError, organization?.id])

  useEffect(() => {
    if (
      !organization?.id
      || !member.data
      || !legal.data
      || legal.data.requires_acceptance
      || navigatedOrganizationId.current === organization.id
    ) return

    navigatedOrganizationId.current = organization.id
    const destination = member.data.foundation_status === 'COMPLETED'
      ? (returnPath || getDefaultRouteForMember(member.data))
      : '/foundation'
    navigate(destination, { replace: true })
  }, [legal.data, member.data, navigate, organization?.id, returnPath])

  const resumeTask = async () => {
    setActionError('')
    try {
      await clerk.redirectToTasks({ redirectUrl: '/create-org' })
    } catch (failure) {
      setActionError(getApiErrorMessage(failure, failure?.message || 'Não foi possível retomar a tarefa de organização.'))
    }
  }

  const retry = () => {
    if (member.isError && isAdmin) {
      attemptedBootstrapOrganizationId.current = null
      startBootstrap()
      return
    }
    if (legal.isError || legal.data?.requires_acceptance) {
      setActionError('')
      void legal.refetch()
      return
    }
    if (member.isError) {
      setActionError('')
      void member.refetch()
    }
  }

  const confirmLegal = async (confirmed) => {
    if (!legal.data || !confirmed) return
    setActionError('')
    try {
      await acceptance.mutateAsync({
        acceptance_confirmed: true,
        terms_version: legal.data.terms_version,
        dpa_version: legal.data.dpa_version,
        privacy_version: legal.data.privacy_version,
      })
    } catch (failure) {
      setActionError(getApiErrorMessage(failure, failure?.message || 'Não foi possível registar a aceitação.'))
    }
  }

  const error = actionError
    || (bootstrapError ? getApiErrorMessage(bootstrapError, bootstrapError.message || 'Não foi possível preparar a organização.') : '')
    || (acceptance.error ? getApiErrorMessage(acceptance.error, acceptance.error.message || 'Não foi possível registar a aceitação.') : '')

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_CREATEORG} stats={BRAND_STATS_CREATEORG} />
        <div className="zen-auth-form-side">
          <div className="zen-auth-form-wrapper">
            <h1 className="h3 mb-3">A preparar a sua escola</h1>
            {error && <div className="alert alert-danger" role="alert">{error}</div>}

            {!organization && <NoActiveOrganization onResumeTask={resumeTask} />}

            {organization && member.isError && isAdmin && (
              <BootstrapState isPending={bootstrapPending} onRetry={retry} />
            )}

            {organization && member.isError && !isAdmin && (
              <NonAdminState onRetry={retry} onSignOut={() => void clerk.signOut({ redirectUrl: '/login' })} />
            )}

            {organization && !member.isError && (member.isLoading || !member.data || bootstrapPending) && (
              <p role="status">A sincronizar a organização e a preparar o onboarding…</p>
            )}

            {organization && member.data && legal.isLoading && (
              <p role="status">A verificar o estado dos documentos legais…</p>
            )}

            {organization && member.data && legal.isError && (
              <RetryState message="Não foi possível verificar os documentos legais." onRetry={retry} />
            )}

            {organization && member.data && legal.data?.requires_acceptance && isAdmin && (
              <LegalAcceptanceForm
                key={`${organization.id}-${legal.data.terms_version}-${legal.data.dpa_version}-${legal.data.privacy_version}`}
                status={legal.data}
                pending={acceptance.isPending}
                onSubmit={confirmLegal}
              />
            )}

            {organization && member.data && legal.data?.requires_acceptance && !isAdmin && (
              <NonAdminState onRetry={retry} onSignOut={() => void clerk.signOut({ redirectUrl: '/login' })} />
            )}

            <div className="zen-auth-form-footer">
              <Link to="/" className="zen-auth-back-link">Voltar ao início</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function NoActiveOrganization({ onResumeTask }) {
  return (
    <div>
      <p>Selecione uma organização ou retome a tarefa de organização do Clerk.</p>
      <div className="mb-3"><OrganizationSwitcher hidePersonal /></div>
      <button type="button" className="btn btn-primary" onClick={() => void onResumeTask()}>
        Retomar tarefa de organização
      </button>
    </div>
  )
}

function BootstrapState({ isPending, onRetry }) {
  return (
    <div role="status">
      {isPending
        ? <p>A sincronizar a organização e a preparar o onboarding…</p>
        : <><p>Não foi possível preparar a organização.</p><button type="button" className="btn btn-primary" onClick={onRetry}>Tentar novamente</button></>}
    </div>
  )
}

function RetryState({ message, onRetry }) {
  return <div role="status"><p>{message}</p><button type="button" className="btn btn-primary" onClick={onRetry}>Tentar novamente</button></div>
}

function NonAdminState({ onRetry, onSignOut }) {
  return (
    <div role="alert">
      <p>Um administrador da organização deve aceitar os documentos legais antes de continuar.</p>
      <div className="d-flex gap-2 flex-wrap">
        <button type="button" className="btn btn-primary" onClick={onRetry}>Atualizar</button>
        <OrganizationSwitcher hidePersonal />
        <button type="button" className="btn btn-link" onClick={onSignOut}>Terminar sessão</button>
      </div>
    </div>
  )
}

function LegalAcceptanceForm({ status, pending, onSubmit }) {
  const [checked, setChecked] = useState(false)

  return (
    <section aria-labelledby="legal-acceptance-title">
      <h2 id="legal-acceptance-title" className="h5">Confirme os documentos legais</h2>
      <p>Para continuar, confirme a aceitação atual da organização.</p>
      <LegalDocuments status={status} />
      <label className="zen-auth-legal-checkbox">
        <input
          type="checkbox"
          aria-label={LEGAL_CONFIRMATION_TEXT}
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
        />
        <span>{LEGAL_CONFIRMATION_TEXT}</span>
      </label>
      <button type="button" className="btn btn-primary mt-3" disabled={!checked || pending} onClick={() => void onSubmit(checked)}>
        {pending ? 'A guardar…' : 'Confirmar e continuar'}
      </button>
    </section>
  )
}

function LegalDocuments({ status }) {
  const documents = [
    ['Termos de Serviço', '/termos', status.terms_version],
    ['Acordo de Tratamento de Dados (DPA)', '/dpa', status.dpa_version],
    ['Política de Privacidade', '/privacidade', status.privacy_version],
  ]
  return (
    <ul aria-label="Documentos legais atuais">
      {documents.map(([label, path, version]) => (
        <li key={path}><Link to={path} target="_blank" rel="noreferrer">{label}</Link> — versão {version}</li>
      ))}
    </ul>
  )
}
