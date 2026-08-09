import { memo } from 'react'
import { navItems } from '../../data/marketingData'

const MarketingFooter = memo(function MarketingFooter() {
  return (
    <footer className="cronos-footer">
      <div className="cronos-layout">
        <div className="cronos-footer__brand">Cronos</div>
        <div className="cronos-footer__grid">
          <div>
            <h2>Navegação</h2>
            {navItems.map((item) => (
              <a href={item.href} key={item.href}>{item.label}</a>
            ))}
          </div>
          <div>
            <h2>Contacto</h2>
            <p>contacto@cronos.pt</p>
            <p>+351 968 348 153</p>
          </div>
          <div>
            <h2>Presença</h2>
            <a href="https://www.linkedin.com" target="_blank" rel="noreferrer">LinkedIn</a>
            <a href="https://www.instagram.com" target="_blank" rel="noreferrer">Instagram</a>
          </div>
        </div>
      </div>
    </footer>
  )
})

export default MarketingFooter
