import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import ResponsivePicture from '../shared/ResponsivePicture'
import DemoCta from '../shared/DemoCta'
import { aboutContent } from '../../content/about'
import { publicIdentity } from '../../content/publicIdentity'

export default function FounderStory() {
  return (
    <>
      <MarketingSection className="cronos-about-story" labelledBy="cronos-about-title">
        <div className="cronos-container cronos-about-story__grid">
          <div className="cronos-about-story__copy">
            <SectionHeading
              as="h1"
              variant="page"
              id="cronos-about-title"
              eyebrow={aboutContent.eyebrow}
              title={aboutContent.title}
            />
            <div className="cronos-about-story__paragraphs">
              {aboutContent.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>
            <blockquote className="cronos-about-story__quote">
              <p>“{aboutContent.quote}”</p>
              <cite className="cronos-about-story__cite">
                <strong>{aboutContent.founder}</strong>
                <span>{aboutContent.role}</span>
              </cite>
            </blockquote>
          </div>
          <figure className="cronos-founder-portrait">
            <div className="cronos-founder-portrait__frame">
              <ResponsivePicture {...aboutContent.image} className="cronos-founder-portrait__picture" />
              <div className="cronos-founder-portrait__badge">
                <strong>{aboutContent.founder}</strong>
                <span>{aboutContent.role}</span>
              </div>
            </div>
          </figure>
        </div>
      </MarketingSection>
      <MarketingSection className="cronos-about-trust" labelledBy="cronos-about-trust-title">
        <div className="cronos-container cronos-about-trust__inner">
          <SectionHeading
            as="h2"
            id="cronos-about-trust-title"
            eyebrow={aboutContent.trust.eyebrow}
            title={aboutContent.trust.title}
          />
          <div className="cronos-about-trust__copy">
            {aboutContent.trust.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            <address>
              <a href={`mailto:${publicIdentity.email}`}>{publicIdentity.email}</a>
              <span>{publicIdentity.address.street}, {publicIdentity.address.postalCode} {publicIdentity.address.locality}</span>
            </address>
          </div>
        </div>
      </MarketingSection>
      <DemoCta source="about" />
    </>
  )
}
