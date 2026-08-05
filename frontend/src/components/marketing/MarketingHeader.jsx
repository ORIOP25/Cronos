import { Fragment, memo } from 'react'
import { navItems } from '../../data/marketingData'

function BrandMark() {
  const handleLogoClick = (e) => {
    e.preventDefault()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <a href="#inicio" onClick={handleLogoClick} className="cronos-brand" aria-label="Cronos - Voltar ao topo">
      <img src="/logo.png" alt="" className="cronos-brand__image" width="48" height="48" decoding="async" />
      <span className="cronos-brand__text">Cronos</span>
    </a>
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
          <span className="cronos-login-link cronos-login-link--disabled" aria-disabled="true">Área reservada — brevemente</span>
          <a href="#contacto" className="cronos-button cronos-button--header">
            Agendar demonstração
          </a>
        </div>
      </div>
    </header>
  )
})

export default MarketingHeader
