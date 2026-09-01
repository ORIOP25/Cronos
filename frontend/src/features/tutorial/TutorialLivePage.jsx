import Subjects from '../../pages/Subjects'
import CourseDetails from '../../pages/CourseDetails'
import Members from '../../pages/Members'
import Rooms from '../../pages/Rooms'
import ClassSubjects from '../../pages/ClassSubjects'
import MyAvailability from '../../pages/MyAvailability'
import Schedules from '../../pages/Schedules'
import Occurrences from '../../pages/Occurrences'
import Timesheets from '../../pages/Timesheets'

export function TutorialLivePage({ step, readOnly = false, allowedActions = [], navigationDisabled = true, referenceDate }) {
  const pageProps = { readOnly, allowedActions, navigationDisabled, referenceDate }
  switch (step.page) {
    case 'Subjects':
      return <Subjects {...pageProps} />
    case 'CourseDetails':
      return <CourseDetails courseIdOverride={1} {...pageProps} />
    case 'Members':
      return <Members {...pageProps} />
    case 'Rooms':
      return <Rooms {...pageProps} />
    case 'ClassSubjects':
      return <ClassSubjects courseIdOverride={1} classIdOverride={1} {...pageProps} />
    case 'MyAvailability':
      return <MyAvailability {...pageProps} warnOnUnsavedChanges={false} />
    case 'Schedules':
      return <Schedules initialClassId={1} initialWeekStart={step.id === 'recovery' ? '2025-09-22' : '2025-09-15'} persistView={false} {...pageProps} />
    case 'Occurrences':
      return <Occurrences tabOverride={step.tab} {...pageProps} />
    case 'Timesheets':
      return <Timesheets initialWeekStart="2025-09-15" {...pageProps} />
    default:
      return null
  }
}
