import { memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight } from '@coreui/icons'
import ServiceStrip from './ServiceStrip'
import ShinyText from './ShinyText'

const HeroSection = memo(function HeroSection() {
  return (
    <section className="cronos-hero" aria-labelledby="cronos-hero-title">
      <div className="cronos-hero-bg-anim" aria-hidden="true" />
      <div className="cronos-layout cronos-hero__grid">
        <div className="cronos-hero__copy">
          <h1 id="cronos-hero-title">
            <ShinyText
              text="Horários para o Ensino"
              color="#3b2415"
              shineColor="#8c5c32"
              speed={5}
              delay={1.5}
              spread={120}
            />
            <br className="cronos-hero-br" />
            <ShinyText
              text="Profissional Português"
              color="#3b2415"
              shineColor="#8c5c32"
              speed={5}
              delay={2}
              spread={120}
            />
          </h1>
          <span className="cronos-title-rule" aria-hidden="true" />
          <p>
            O Cronos é uma aplicação para escolas portuguesas com ensino profissional. Criámo-lo para aliviar a direção, a secretaria e os professores. Geramos horários sem conflitos em minutos, resolvemos furos de última hora e acompanhamos as horas das UFCDs num único lugar, de forma simples e transparente.
          </p>
          <div className="cronos-hero__actions">
            <a href="#contacto" className="cronos-button">
              Marcar conversa de 15 minutos! <CIcon icon={cilArrowRight} />
            </a>
            <a href="#rotina" className="cronos-button cronos-button--secondary">
              Ver como funcionará o meu dia a dia
            </a>
          </div>
        </div>

        <figure className="cronos-hero__visual">
          <picture>
            <source srcSet="/marketing/hero-laptop.webp" type="image/webp" />
            <img
              src="/marketing/hero-laptop.png"
              alt="Interface Cronos aberta num computador portátil"
              width="420"
              height="512"
              loading="eager"
              decoding="async"
            />
          </picture>
        </figure>
      </div>

      <ServiceStrip />
    </section>
  )
})

export default HeroSection
