import { Fragment, memo } from 'react'
import { Link } from 'react-router-dom'
import { navItems } from '../../data/marketingData'

function BrandMark() {
  return (
    <Link to="/" className="cronos-brand" aria-label="Cronos">
      <img src="/logo.png" alt="" className="cronos-brand__image" width="48" height="48" decoding="async" />
      <span className="cronos-brand__text">Cronos</span>
    </Link>
  )
}

const MarketingHeader = memo(function MarketingHeader() {
  return (
    <header className="cronos-header" id="inicio">
      <div className="cronos-header__inner">
        <BrandMark />
        <nav className="cronos-nav" aria-label="Navegação principal">
          {navItems.map((item, index) => (
            <Fragment key={item.href}>
              <a href={item.href}>{item.label}</a>
              {index < navItems.length - 1 && <span aria-hidden="true">•</span>}
            </Fragment>
          ))}
        </nav>
        <div className="cronos-header__actions">
          <Link to="/login" className="cronos-login-link">Entrar</Link>
          <a href="#contacto" className="cronos-button cronos-button--header">
            Agendar demonstração
          </a>
        </div>
      </div>
    </header>
  )
})

export default MarketingHeader
