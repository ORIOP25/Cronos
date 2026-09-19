import { Link } from 'react-router-dom'
import { cilArrowRight } from '@coreui/icons'
import CIconModule from '@coreui/icons-react'
import { homeHero } from '../../content/home'
import ResponsivePicture from '../shared/ResponsivePicture'
import MarketingSection from '../shared/MarketingSection'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

export default function HeroSection() {
  return (
    <MarketingSection className="cronos-hero">
      <div className="cronos-container cronos-hero__grid">
        <div className="cronos-hero__copy">
          {homeHero.eyebrow && <p className="cronos-eyebrow">{homeHero.eyebrow}</p>}
          <h1>{homeHero.title}</h1>
          <p className="cronos-hero__body">{homeHero.body}</p>
          <div className="cronos-hero__actions">
            <Link to="/contacto" className="cronos-button">Pedir demonstração <CIcon icon={cilArrowRight} /></Link>
            <Link to="/como-funciona" className="cronos-button cronos-button--secondary">Ver como funciona</Link>
          </div>
        </div>
        <div className="cronos-hero__visual">
          <div className="cronos-hero__frame">
            <ResponsivePicture {...homeHero.image} loading="eager" fetchPriority="high" className="cronos-hero__picture" />
          </div>
        </div>
      </div>
    </MarketingSection>
  )
}
