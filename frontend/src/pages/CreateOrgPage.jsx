import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useOrganizationList, useUser } from '@clerk/react'
import BrandPanel from '../components/auth/BrandPanel'
import { useCreateActiveOrganization } from '../features/organization/useCreateActiveOrganization'
import { getPendingOrganizationKey } from '../features/organization/activateAndBootstrapOrganization'
import {
  BRAND_STATS_CREATEORG,
  BRAND_TAGLINE_CREATEORG,
} from '../utils/authDesign'


export default function CreateOrgPage() {
  const { isLoaded, userMemberships } = useOrganizationList({
    userMemberships: { infinite: true },
  })
  const { user } = useUser()
  const { run, isPending, error } = useCreateActiveOrganization()
  const [name, setName] = useState('')
  const pendingKey = getPendingOrganizationKey(user?.id)
  const pendingOrganizationId = pendingKey ? sessionStorage.getItem(pendingKey) : null
  const memberships = userMemberships?.data || []
  const membershipsLoading = !isLoaded || userMemberships?.isLoading || userMemberships?.isFetching

  const submit = async (event) => {
    event.preventDefault()
    await run({ name }).catch(() => {})
  }

  const retry = () => run({ organizationId: pendingOrganizationId }).catch(() => {})

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_CREATEORG} stats={BRAND_STATS_CREATEORG} />
        <div className="zen-auth-form-side">
          <div className="zen-auth-form-wrapper">
            <h1 className="h3 mb-3">Organização escolar</h1>
            {membershipsLoading && <p>A carregar organizações…</p>}
            {error && (
              <div className="alert alert-danger" role="alert">
                Não foi possível ativar a organização. Pode tentar novamente sem criar outra.
              </div>
            )}
            {!membershipsLoading && pendingOrganizationId ? (
              <button type="button" className="btn btn-primary" disabled={isPending} onClick={retry}>
                {isPending ? 'A ativar…' : 'Retomar ativação'}
              </button>
            ) : !membershipsLoading && memberships.length ? (
              <div>
                <p>Selecione a organização que pretende utilizar.</p>
                <div className="d-grid gap-2">
                  {memberships.map((membership) => (
                    <button
                      type="button"
                      className="btn btn-outline-primary"
                      disabled={isPending}
                      key={membership.organization.id}
                      onClick={() => run({ organizationId: membership.organization.id }).catch(() => {})}
                    >
                      {membership.organization.name}
                    </button>
                  ))}
                </div>
              </div>
            ) : !membershipsLoading ? (
              <form onSubmit={submit}>
                <label htmlFor="organization-name" className="form-label">Nome da escola</label>
                <input
                  id="organization-name"
                  className="form-control mb-3"
                  required
                  minLength={2}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <button type="submit" className="btn btn-primary w-100" disabled={isPending}>
                  {isPending ? 'A criar e ativar…' : 'Criar organização'}
                </button>
              </form>
            ) : null}
            <div className="zen-auth-form-footer">
              <Link to="/" className="zen-auth-back-link">Voltar ao início</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
