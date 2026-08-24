import Subjects from '../../pages/Subjects'
import Courses from '../../pages/Courses'
import Members from '../../pages/Members'
import Rooms from '../../pages/Rooms'
import ClassSubjects from '../../pages/ClassSubjects'
import MyAvailability from '../../pages/MyAvailability'
import Schedules from '../../pages/Schedules'
import Occurrences from '../../pages/Occurrences'
import Timesheets from '../../pages/Timesheets'
import { PreparationDashboard } from '../dashboard/PreparationDashboard'

const DEMO_BASES = {
  percentage: 71,
  depth: 5,
  complete: false,
  steps: [
    { code: 'ACTIVE_CLASSES', status: 'COMPLETE', route: '/courses' },
    { code: 'CLASS_SUBJECTS', status: 'COMPLETE', route: '/classes' },
    { code: 'MODULES', status: 'COMPLETE', route: '/subjects' },
    { code: 'TEACHER_ASSIGNMENT', status: 'COMPLETE', route: '/members' },
    { code: 'COMPATIBLE_ROOM', status: 'COMPLETE', route: '/rooms' },
    { code: 'TIMESLOTS', status: 'PENDING', route: '/config' },
    { code: 'TEACHER_AVAILABILITY', status: 'PENDING', route: '/members' },
  ],
}

export function TutorialLivePage({ step }) {
  switch (step.id) {
    case 'structure_overview':
      return <PreparationDashboard orgId="demo-org" userId="demo-user" organizationName="Escola Profissional Demo" bases={DEMO_BASES} autoStartGuide={false} />
    case 'subject_create':
    case 'module_add':
      return <Subjects />
    case 'course_create':
    case 'class_create':
      return <Courses />
    case 'teacher_add':
    case 'teacher_competency':
      return <Members />
    case 'room_add':
      return <Rooms />
    case 'assignment_create':
      return <ClassSubjects courseIdOverride={1} classIdOverride={1} navigationDisabled />
    case 'availability_review':
      return <MyAvailability />
    case 'schedule_prepare':
    case 'schedule_review':
    case 'schedule_approve':
    case 'chapter_transition':
    case 'published_block_open':
    case 'repair_simulate':
    case 'repair_compare':
    case 'history_verify':
    case 'repair_approve':
    case 'occurrence_create':
      return <Schedules initialClassId={1} persistView={false} />
    case 'substitute_teacher_select':
    case 'substitute_subject_select':
    case 'substitution_complete':
      return <Occurrences />
    case 'debt_observe':
      return <Timesheets />
    default:
      return null
  }
}
