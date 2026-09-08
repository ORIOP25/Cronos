import { useCallback, useEffect, useState } from 'react'
import { OrganizationSwitcher, useClerk, useOrganization } from '@clerk/react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useCurrentMember } from '../features/members/data'
import { useAcceptLegalDocuments, useLegalStatus } from '../features/legal/data'
import { getApiErrorMessage } from '../utils/apiErrors'
import { PageLoader } from '../routeGuards'

const initialForm = {
  controller_legal_name: '',
  controller_registration_number: '',
  controller_registered_address: '',
  controller_contact_email: '',
  representative_name: '',
  representative_role: '',
  authority_confirmed: false,
  terms_accepted: false,
  dpa_accepted: false,
}

function safeInternalReturnPath(value, fallback) {
  return typeof value === 'string'
    && value.startsWith('/')
    && !value.startsWith('//')
    && !value.includes('://')
    ? value
    : fallback
}

export default function LegalAcceptancePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const clerk = useClerk()
  const { organization, isLoaded: organizationLoaded } = useOrganization()
  const member = useCurrentMember({ enabled: Boolean(organization) })
  const legal = useLegalStatus({ enabled: Boolean(organization) })
  const accept = useAcceptLegalDocuments()
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const continueAfterAcceptance = useCallback(() => {
    const fallback = member.data?.foundation_status === 'COMPLETED' ? '/dashboard' : '/foundation'
    const destination = safeInternalReturnPath(location.state?.from, fallback)
    navigate(destination, { replace: true })
  }, [location.state, member.data?.foundation_status, navigate])

  useEffect(() => {
    if (organizationLoaded && !organization) navigate('/create-org', { replace: true })
  }, [navigate, organization, organizationLoaded])

  useEffect(() => {
    if (legal.data?.accepted && member.data) continueAfterAcceptance()
  }, [continueAfterAcceptance, legal.data?.accepted, member.data])

  if (!organizationLoaded) return <PageLoader />
  if (!organization) return null
  if (member.isLoading || legal.isLoading) return <PageLoader />
  if (member.isError || legal.isError) return <ErrorPanel onRetry={() => { void member.refetch(); void legal.refetch() }} />
  if (!member.data) return <PageLoader />

  const isAdmin = member.data.capabilities?.includes('admin')
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!form.authority_confirmed || !form.terms_accepted || !form.dpa_accepted) {
      setError('Confirme a autoridade, os Termos de Serviço e o Acordo de Tratamento de Dados.')
      return
    }
    if (!legal.data?.terms_version || !legal.data?.dpa_version) {
      setError('As versões legais ainda não estão disponíveis. Atualize a página e tente novamente.')
      return
    }
    try {
      await accept.mutateAsync({
        controller_legal_name: form.controller_legal_name,
        controller_registration_number: form.controller_registration_number,
        controller_registered_address: form.controller_registered_address,
        controller_contact_email: form.controller_contact_email,
        representative_name: form.representative_name,
        representative_role: form.representative_role,
        authority_confirmed: true,
        terms_accepted: true,
        dpa_accepted: true,
        terms_version: legal.data.terms_version,
        dpa_version: legal.data.dpa_version,
      })
      continueAfterAcceptance()
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, 'Não foi possível registar a aceitação.'))
      if (requestError?.response?.status === 409) {
        setForm((current) => ({
          ...current,
          authority_confirmed: false,
          terms_accepted: false,
          dpa_accepted: false,
        }))
        void legal.refetch()
      }
    }
  }

  return (
    <div className="zen-auth-page legal-acceptance-page">
      <main className="legal-acceptance-card" aria-labelledby="legal-acceptance-title">
        <p className="cronos-eyebrow">{organization?.name || 'Organização'}</p>
        <h1 id="legal-acceptance-title">Antes de configurar a escola</h1>
        {isAdmin ? (
          <form onSubmit={submit} noValidate>
            <p>Confirme os dados da entidade e aceite os Termos de Serviço e o Acordo de Tratamento de Dados em nome da organização.</p>
            <Field id="controller_legal_name" label="Nome legal da entidade" value={form.controller_legal_name} onChange={update} required />
            <Field id="controller_registration_number" label="NIF/NIPC" value={form.controller_registration_number} onChange={update} required />
            <Field id="controller_registered_address" label="Morada registada" value={form.controller_registered_address} onChange={update} required />
            <Field id="controller_contact_email" type="email" label="Email de contacto" value={form.controller_contact_email} onChange={update} required />
            <Field id="representative_name" label="Nome do representante" value={form.representative_name} onChange={update} required />
            <Field id="representative_role" label="Cargo do representante" value={form.representative_role} onChange={update} required />
            <label className="form-check"><input className="form-check-input" type="checkbox" checked={form.authority_confirmed} onChange={(event) => update('authority_confirmed', event.target.checked)} /><span>Confirmo que tenho poderes para vincular esta organização.</span></label>
            <label className="form-check"><input className="form-check-input" type="checkbox" checked={form.terms_accepted} onChange={(event) => update('terms_accepted', event.target.checked)} /><span>Li e aceito os <a href="/termos" target="_blank" rel="noreferrer">Termos de Serviço</a>, versão {legal.data?.terms_version}.</span></label>
            <label className="form-check"><input className="form-check-input" type="checkbox" checked={form.dpa_accepted} onChange={(event) => update('dpa_accepted', event.target.checked)} /><span>Li e aceito o <a href="/dpa" target="_blank" rel="noreferrer">Acordo de Tratamento de Dados</a>, versão {legal.data?.dpa_version}.</span></label>
            <p className="legal-acceptance-note">A <a href="/privacidade" target="_blank" rel="noreferrer">Política de Privacidade</a> é informação e não exige um consentimento separado.</p>
            {error && <p className="alert alert-danger" role="alert">{error}</p>}
            <button className="btn btn-primary" type="submit" disabled={accept.isPending}>{accept.isPending ? 'A registar…' : 'Aceitar e continuar'}</button>
          </form>
        ) : (
          <div>
            <p>Um administrador autorizado deve aceitar os documentos legais antes de continuar.</p>
            <button className="btn btn-outline-primary" type="button" onClick={() => void legal.refetch()}>Verificar novamente</button>
          </div>
        )}
        <div className="legal-acceptance-actions"><button className="btn btn-link" type="button" onClick={() => void clerk.signOut({ redirectUrl: '/' })}>Terminar sessão</button><OrganizationSwitcher hidePersonal /></div>
      </main>
    </div>
  )
}

function Field({ id, label, value, onChange, type = 'text', required = false }) {
  return <label className="legal-acceptance-field" htmlFor={id}><span>{label}</span><input id={id} name={id} type={type} value={value} required={required} onChange={(event) => onChange(id, event.target.value)} /></label>
}

function ErrorPanel({ onRetry }) {
  return <div className="container py-5 text-center" role="alert"><p>Não foi possível verificar o estado jurídico da organização.</p><button type="button" className="btn btn-primary" onClick={onRetry}>Tentar novamente</button></div>
}
