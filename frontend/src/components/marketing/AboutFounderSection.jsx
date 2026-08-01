import { memo } from 'react'

const AboutFounderSection = memo(function AboutFounderSection() {
  return (
    <section className="cronos-about" id="sobre" aria-labelledby="cronos-about-title">
      <div className="cronos-layout cronos-about__grid">
        <div className="cronos-about__content">
          <span className="cronos-about__subtitle">Sobre o Cronos</span>
          <h2 id="cronos-about-title">Nascido da experiência real no Ensino Profissional</h2>
          <p>
            O Cronos nasceu da experiência direta no Ensino Profissional. Como antigo aluno, vivenciei em primeira mão o impacto de horários instáveis, salas sobrepostas e a falta de previsibilidade no cumprimento dos módulos.
          </p>
          <p>
            Decidi criar o Cronos para transformar essa realidade: uma plataforma centralizada e inteligente que liga o planeamento da direção à rotina da sala de aula, devolvendo o controlo às escolas e a tranquilidade a professores e alunos.
          </p>

          <blockquote className="cronos-about-quote">
            <p>
              “O objetivo nunca foi apenas gerar horários, mas dar às escolas a tranquilidade que precisam para se focarem no essencial: o sucesso dos alunos.”
            </p>
            <cite>
              <strong>Rodrigo Manguinhas</strong>
              <span>Fundador & CEO</span>
            </cite>
          </blockquote>
        </div>

        <div className="cronos-about__portrait-wrap">
          <picture>
            <source srcSet="/marketing/founder-portrait.webp" type="image/webp" />
            <img
              src="/marketing/founder-portrait.png"
              alt="Retrato de Rodrigo Manguinhas, Fundador & CEO do Cronos"
              className="cronos-about__portrait-image"
              width="440"
              height="550"
              loading="lazy"
              decoding="async"
            />
          </picture>
          <div className="cronos-about__portrait-badge">
            <strong>Rodrigo Manguinhas</strong>
            <span>Fundador & CEO</span>
          </div>
        </div>
      </div>
    </section>
  )
})

export default AboutFounderSection
