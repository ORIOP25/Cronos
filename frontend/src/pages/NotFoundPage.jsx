import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@clerk/react'

export default function NotFoundPage() {
  const location = useLocation()
  const { isSignedIn } = useAuth()

  return (
    <main className="zen-not-found-page">
      <section className="zen-not-found-inner" aria-labelledby="not-found-title">
        <h1 id="not-found-title" className="zen-not-found-title">Página não encontrada</h1>
        <p className="zen-not-found-copy">
          Não encontrámos a página <strong>{location.pathname}</strong>. Pode ter sido movida ou o endereço pode estar incompleto.
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
        <h1 id="not-found-title" className="zen-not-found-title">Página não encontrada</h1>
        <p className="zen-not-found-copy">A página pedida não existe ou deixou de estar disponível. Volte ao início para continuar.</p>
        <div className="zen-not-found-actions">
          <a href="/" className="btn-zen btn-zen-primary">Voltar ao início</a>
          <a href="/sitemap.xml" className="btn-zen btn-zen-outline">Ver mapa do site</a>
        </div>
      </section>
    </main>
  )
}
