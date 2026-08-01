import { memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight } from '@coreui/icons'
import { serviceTiles } from '../../data/marketingData'

const ServiceStrip = memo(function ServiceStrip() {
  return (
    <div className="cronos-layout cronos-service-strip" aria-label="Principais áreas do Cronos">
      {serviceTiles.map((tile) => (
        <a href={tile.href} key={tile.title} className="cronos-service-tile">
          <h3>{tile.title}</h3>
          <p>{tile.text}</p>
          <span className="cronos-service-tile__link">
            Saber mais <CIcon icon={cilArrowRight} />
          </span>
        </a>
      ))}
    </div>
  )
})

export default ServiceStrip
