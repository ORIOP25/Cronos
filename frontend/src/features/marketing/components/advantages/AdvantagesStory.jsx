import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import DemoCta from '../shared/DemoCta'
import { advantagesIntro, lossesVsGains, softSkillPillars } from '../../content/advantages'

export default function AdvantagesStory() {
  return (
    <>
      <MarketingSection className="cronos-page-intro" labelledBy="cronos-advantages-title">
        <div className="cronos-container cronos-narrow">
          <SectionHeading
            as="h1"
            variant="page"
            id="cronos-advantages-title"
            eyebrow={advantagesIntro.eyebrow}
            title={advantagesIntro.title}
            body={advantagesIntro.body}
            align="center"
          />
        </div>
      </MarketingSection>

      <MarketingSection className="cronos-advantages-comparison">
        <div className="cronos-container">
          <h2 className="visually-hidden">Comparação entre a gestão manual e o Cronos</h2>
          <div className="cronos-advantages-comparison__grid">
            {lossesVsGains.map((item) => (
              <div key={item.id} className="cronos-comparison-card">
                <div className="cronos-comparison-card__side cronos-comparison-card__side--loss">
                  <div className="cronos-comparison-card__banner cronos-comparison-card__banner--loss">
                    <span>Sem o Cronos</span>
                    <span className="cronos-comparison-card__icon">✕</span>
                  </div>
                  <div className="cronos-comparison-card__body">
                    <h3>{item.lossTitle}</h3>
                    <p>{item.lossText}</p>
                  </div>
                </div>
                <div className="cronos-comparison-card__side cronos-comparison-card__side--gain">
                  <div className="cronos-comparison-card__banner cronos-comparison-card__banner--gain">
                    <span>Com o Cronos</span>
                    <span className="cronos-comparison-card__icon">✓</span>
                  </div>
                  <div className="cronos-comparison-card__body">
                    <h3>{item.gainTitle}</h3>
                    <p>{item.gainText}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </MarketingSection>

      <MarketingSection className="cronos-advantages-impact">
        <div className="cronos-container">
          <SectionHeading
            as="h2"
            id="cronos-impact-title"
            eyebrow="Impacto na comunidade escolar"
            title="Tranquilidade e harmonia para quem faz a escola acontecer"
            align="center"
          />
          <div className="cronos-advantages-impact__grid">
            {softSkillPillars.map((pillar) => (
              <article key={pillar.id} className="cronos-impact-card">
                <span className="cronos-impact-card__role">{pillar.role}</span>
                <h3>{pillar.title}</h3>
                <p>{pillar.text}</p>
              </article>
            ))}
          </div>
        </div>
      </MarketingSection>

      <DemoCta source="advantages" />
    </>
  )
}
