import { Link } from 'react-router-dom'
import { contactDetails, navigationItems } from '../../content/navigation'

export default function MarketingFooter() {
  return (
    <footer className="cronos-footer">
      <div className="cronos-container cronos-footer__inner">
        <div className="cronos-footer__brand">
          <span className="cronos-brand__text">Cronos</span>
          <p>Horários desenhados para o Ensino Profissional Português.</p>
        </div>
        <div className="cronos-footer__column">
          <h2>Navegação</h2>
          <div className="cronos-footer__links">
            {navigationItems.map((item) => <Link key={item.id} to={item.path}>{item.label}</Link>)}
          </div>
        </div>
        <div className="cronos-footer__column">
          <h2>Contacto</h2>
          {contactDetails.map((detail) => <a key={detail.id} href={detail.href}>{detail.value}</a>)}
        </div>
        <div className="cronos-footer__column">
          <h2>Legal</h2>
          <Link to="/privacidade">Privacidade</Link>
          <Link to="/termos">Termos</Link>
          <Link to="/dpa">DPA</Link>
          <Link to="/cookies">Cookies</Link>
        </div>
      </div>
    </footer>
  )
}
