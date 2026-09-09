import { useEffect, useRef, useState } from 'react'
import { useAuth, useOrganization } from '@clerk/react'
import { Link, useLocation } from 'react-router-dom'
import BrandPanel from '../components/auth/BrandPanel'
import { clearLegalAcceptance, hasLegalAcceptance } from '../features/legal/acceptanceStorage'
import { useCreateActiveOrganization } from '../features/organization/useCreateActiveOrganization'
import { getApiErrorMessage } from '../utils/apiErrors'
import {
  BRAND_STATS_CREATEORG,
  BRAND_TAGLINE_CREATEORG,
} from '../utils/authDesign'

function safeInternalReturnPath(value, fallback) {
  return typeof value === 'string'
    && value.startsWith('/')
    && !value.startsWith('//')
    && !value.includes('://')
    ? value
    : fallback
}

export default function CreateOrgPage() {
  const location = useLocation()
  const { userId } = useAuth()
  const { organization } = useOrganization()
  const { run, isPending, error } = useCreateActiveOrganization()
  const [activationError, setActivationError] = useState('')
  const attemptedOrganizationId = useRef(null)
  const returnPath = safeInternalReturnPath(location.state?.from, '')
  const legalAccepted = hasLegalAcceptance(userId)
  const organizationIsPending = Boolean(organization?.id && isPending)

  useEffect(() => {
    if (!organization?.id || !legalAccepted || attemptedOrganizationId.current === organization.id) return undefined

    const organizationId = organization.id
    attemptedOrganizationId.current = organizationId
    run({
      name: organization.name,
      organizationId,
      acceptance_confirmed: true,
      returnPath,
    })
      .then(() => clearLegalAcceptance(userId))
      .catch((failure) => {
        setActivationError(getApiErrorMessage(failure, failure?.message || 'Não foi possível ativar a organização.'))
      })
  }, [legalAccepted, organization?.id, organization?.name, returnPath, run, userId])

  const displayedError = activationError
    || (error ? getApiErrorMessage(error, error.message || 'Não foi possível concluir a ação.') : '')

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_CREATEORG} stats={BRAND_STATS_CREATEORG} />
        <div className="zen-auth-form-side">
          <div className="zen-auth-form-wrapper">
            <h1 className="h3 mb-3">A preparar a sua escola</h1>
            {displayedError && (
              <div className="alert alert-danger" role="alert">
                {displayedError}
              </div>
            )}
            {organizationIsPending && <p role="status">A sincronizar a organização e a preparar o onboarding…</p>}
            {!organization && <p role="status">A aguardar a organização selecionada…</p>}
            <div className="zen-auth-form-footer">
              <Link to="/" className="zen-auth-back-link">Voltar ao início</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
