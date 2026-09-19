import { cilCalendar, cilCheckCircle, cilClock, cilLayers, cilSchool, cilTask } from '@coreui/icons'
import CIconModule from '@coreui/icons-react'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

const iconMap = {
  calendar: cilCalendar,
  check: cilCheckCircle,
  clock: cilClock,
  layers: cilLayers,
  school: cilSchool,
  task: cilTask,
}

export default function SemanticIcon({ name, ...props }) {
  return <CIcon icon={iconMap[name] || cilTask} {...props} />
}
