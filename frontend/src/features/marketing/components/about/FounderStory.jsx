import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import ResponsivePicture from '../shared/ResponsivePicture'
import DemoCta from '../shared/DemoCta'
import { aboutContent } from '../../content/about'

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
      <DemoCta source="about" />
    </>
  )
}
