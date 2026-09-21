import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import ResponsivePicture from '../shared/ResponsivePicture'
import { people } from '../../content/home'

export default function PeopleSection() {
  return (
    <MarketingSection className="cronos-people" labelledBy="cronos-people-title">
      <div className="cronos-container">
        <SectionHeading id="cronos-people-title" title="Feito para quem mantém a escola a funcionar" align="center" />
        <div className="cronos-people__gallery">
          {[people.primary, ...people.secondary].map((person) => (
            <article className="cronos-person" key={person.id}>
              <div className="cronos-person__picture-wrap">
                <ResponsivePicture {...person.image} loading="eager" className="cronos-person__picture" />
              </div>
              <div className="cronos-person__caption">
                <h3>{person.title}</h3>
                <p>{person.text}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </MarketingSection>
  )
}
