import MarketingHeader from '../components/marketing/MarketingHeader'
import HeroSection from '../components/marketing/HeroSection'
import ProductValueSection from '../components/marketing/ProductValueSection'
import ProcessStepperSection from '../components/marketing/ProcessStepperSection'
import GeneratorSection from '../components/marketing/GeneratorSection'
import RoutineSection from '../components/marketing/RoutineSection'
import RolesSection from '../components/marketing/RolesSection'
import AboutFounderSection from '../components/marketing/AboutFounderSection'
import TestimonialsMarquee from '../components/marketing/TestimonialsMarquee'
import ContactQuestionnaire from '../components/marketing/ContactQuestionnaire'
import MarketingFooter from '../components/marketing/MarketingFooter'
import './MarketingSite.css'

export default function MarketingSite() {
  return (
    <div className="cronos-marketing">
      <MarketingHeader />
      <main>
        <HeroSection />
        <ProductValueSection />
        <ProcessStepperSection />
        <GeneratorSection />
        <RoutineSection />
        <RolesSection />
        <AboutFounderSection />
        <TestimonialsMarquee />
        <ContactQuestionnaire />
      </main>
      <MarketingFooter />
    </div>
  )
}
