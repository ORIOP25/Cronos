import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@clerk/react'

export default function NotFoundPage() {
  const location = useLocation()
  const { isSignedIn } = useAuth()

  return <NotFoundContent isSignedIn={isSignedIn} pathname={location.pathname} />
}

export function NotFoundContent({ isSignedIn = false, pathname = '' }) {
  return (
    <main className="zen-not-found-page">
      <section className="zen-not-found-inner" aria-labelledby="not-found-title">
        <p className="zen-not-found-kicker">404</p>
        <h1 id="not-found-title" className="zen-not-found-title">Página não encontrada</h1>
        <p className="zen-not-found-copy">
          Não encontrámos a página <strong>{pathname}</strong>. Pode ter sido movida ou o endereço pode estar incompleto.
        </p>
        <div className="zen-not-found-actions">
          <Link to={isSignedIn ? '/dashboard' : '/'} className="btn-zen btn-zen-primary">
            {isSignedIn ? 'Ir para o painel' : 'Voltar ao início'}
          </Link>
          {!isSignedIn && <Link to="/login" className="btn-zen btn-zen-outline">Entrar</Link>}
        </div>
      </section>
    </main>
  )
}

export function StaticNotFoundPage() {
  return (
    <main className="zen-not-found-page">
      <section className="zen-not-found-inner" aria-labelledby="not-found-title">
        <p className="zen-not-found-kicker">404</p>
        <h1 id="not-found-title" className="zen-not-found-title">Página não encontrada</h1>
        <p className="zen-not-found-copy">O recurso pedido não existe ou deixou de estar disponível. Consulte uma página pública para continuar.</p>
        <div className="zen-not-found-actions">
          <a href="/" className="btn-zen btn-zen-primary">Voltar ao início</a>
          <a href="/llms.txt" className="btn-zen btn-zen-outline">Ler informação para agentes</a>
          <a href="/sitemap.xml" className="btn-zen btn-zen-outline">Ver mapa do site</a>
        </div>
      </section>
    </main>
  )
}
