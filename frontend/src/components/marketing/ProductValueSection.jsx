import { memo } from 'react'
import CIcon from '@coreui/icons-react'
import { productModules } from '../../data/marketingData'

const ProductValueSection = memo(function ProductValueSection() {
  return (
    <section className="cronos-product" id="produto" aria-labelledby="cronos-product-title">
      <div className="cronos-layout">
        <div className="cronos-section-heading cronos-section-heading--split">
          <h2 id="cronos-product-title">Porque o Cronos é uma mais-valia?</h2>
          <p>
            Sabemos que o ensino profissional é dinâmico e exigente. O Cronos liga o planeamento à sala de aula para que toda a equipa saiba exatamente onde está a cada momento.
          </p>
        </div>

        <div className="cronos-product-grid">
          {productModules.map((module) => (
            <article className="cronos-module-card" key={module.title}>
              <div className="cronos-module-card__icon-wrap">
                <CIcon icon={module.icon} />
              </div>
              <div className="cronos-module-card__body">
                <h3>{module.title}</h3>
                <p>{module.text}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
})

export default ProductValueSection
