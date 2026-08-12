import HeroSection from '../../features/marketing/components/home/HeroSection'
import ProblemCascadeSection from '../../features/marketing/components/home/ProblemCascadeSection'
import MinuteWorkflowSection from '../../features/marketing/components/home/MinuteWorkflowSection'
import AdaptiveScheduleSection from '../../features/marketing/components/home/AdaptiveScheduleSection'
import PeopleSection from '../../features/marketing/components/home/PeopleSection'
import DemoCta from '../../features/marketing/components/shared/DemoCta'

export default function HomePage() {
  return (
    <>
      <HeroSection />
      <ProblemCascadeSection />
      <MinuteWorkflowSection />
      <AdaptiveScheduleSection />
      <PeopleSection />
      <DemoCta source="home" />
    </>
  )
}
