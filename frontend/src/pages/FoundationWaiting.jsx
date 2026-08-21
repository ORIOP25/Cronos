import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOrganization } from '@clerk/react'
import { useCurrentMember } from '../features/members/data'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'

export default function FoundationWaiting() {
  const navigate = useNavigate()
  const { organization } = useOrganization()
  const memberQuery = useCurrentMember({ refetchInterval: 30_000 })

  useEffect(() => {
    if (memberQuery.data?.foundation_status === 'COMPLETED') {
      navigate('/dashboard', { replace: true })
    }
  }, [memberQuery.data?.foundation_status, navigate])

  if (memberQuery.isLoading) {
    return <StatePanel state="loading" title="A verificar a fundação da escola" description="Aguarde enquanto um administrador conclui a configuração base." />
  }

  if (memberQuery.isError) {
    return <StatePanel state="error" title="Não foi possível verificar o estado" description="Tente novamente dentro de instantes." action={<button type="button" className="btn btn-primary" onClick={() => void memberQuery.refetch()}>Tentar novamente</button>} />
  }

  return (
    <div className="container py-5">
      <PageHeader preTitle="Acesso pendente" title="A escola ainda está a ser configurada" context={`Escola: ${organization?.name || 'a sua escola'}`} />
      <p role="status">As áreas operacionais ficarão disponíveis depois de a fundação escolar ser concluída por um administrador.</p>
    </div>
  )
}
