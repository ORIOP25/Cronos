import React from 'react'
import { Link, useLocation } from 'react-router-dom'

export default function NotFoundPage() {
  const location = useLocation()

  return (
    <main className="zen-not-found-page">
      <section className="zen-not-found-inner" aria-labelledby="not-found-title">
        <p className="zen-not-found-kicker">404</p>
        <h1 id="not-found-title" className="zen-not-found-title">Página não encontrada</h1>
        <p className="zen-not-found-copy">
          Não encontrámos a página <strong>{location.pathname}</strong>. Pode ter sido movida ou o endereço pode estar incompleto.
        </p>
        <div className="zen-not-found-actions">
          <Link to="/" className="btn-zen btn-zen-primary">Voltar ao início</Link>
          <Link to="/login" className="btn-zen btn-zen-outline">Entrar</Link>
        </div>
      </section>
    </main>
  )
}
