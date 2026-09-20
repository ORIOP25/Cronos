import { Link, NavLink } from 'react-router-dom'
import CIconModule from '@coreui/icons-react'
import { cilMenu, cilX } from '@coreui/icons'
import { navigationItems } from '../../content/navigation'
import { useMobileMenu } from '../../hooks/useMobileMenu'
import { publicAsset } from '../../../../utils/publicAsset'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

export default function MarketingHeader() {
  const { isOpen, toggleReference, toggleMenu, closeMenu } = useMobileMenu()

  return (
    <header className="cronos-header">
      <div className="cronos-container cronos-header__inner">
        <Link to="/" className="cronos-brand" onClick={closeMenu} aria-label="Cronos, página inicial">
          <img src={publicAsset('/logo.png')} alt="Cronos — Logótipo" width="40" height="40" decoding="async" />
          <span>Cronos</span>
        </Link>
        <button ref={toggleReference} type="button" className="cronos-mobile-toggle" onClick={toggleMenu} aria-expanded={isOpen} aria-controls="cronos-navigation" aria-label={isOpen ? 'Fechar menu de navegação' : 'Abrir menu de navegação'}>
          <CIcon icon={isOpen ? cilX : cilMenu} size="lg" />
        </button>
        <nav id="cronos-navigation" className={`cronos-nav ${isOpen ? 'is-open' : ''}`} aria-label="Navegação principal">
          {navigationItems.map((item) => (
            <NavLink key={item.id} to={item.path} end={item.path === '/'} onClick={closeMenu} className={({ isActive }) => `cronos-nav__link ${isActive ? 'is-active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
          <span className="cronos-reserved-area" aria-disabled="true">Área reservada: brevemente</span>
          <Link to="/contacto" className="cronos-button cronos-button--header" onClick={closeMenu}>Pedir demonstração</Link>
        </nav>
      </div>
    </header>
  )
}
