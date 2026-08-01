import { memo } from 'react'
import { roleCards } from '../../data/marketingData'

const RolesSection = memo(function RolesSection() {
  return (
    <section className="cronos-roles" id="perfis" aria-labelledby="cronos-roles-title">
      <div className="cronos-layout">
        <div className="cronos-section-heading cronos-section-heading--center">
          <h2 id="cronos-roles-title">Cada perfil sabe o que tem de fazer</h2>
          <p>
            O Cronos separa responsabilidades sem separar informação. A direção acompanha, a secretaria organiza e os professores executam o registo diário.
          </p>
        </div>
        <div className="cronos-role-grid">
          {roleCards.map((role) => (
            <article className="cronos-role-card" key={role.title}>
              <div className="cronos-role-card__image-wrap">
                <picture>
                  <source srcSet={role.image} type="image/webp" />
                  <img
                    src={role.fallbackImage}
                    alt={role.title}
                    className="cronos-role-card__image"
                    width="380"
                    height="240"
                    loading="lazy"
                    decoding="async"
                  />
                </picture>
              </div>
              <div className="cronos-role-card__body">
                <h3>{role.title}</h3>
                <p>{role.text}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
})

export default RolesSection
