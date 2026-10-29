import {
  cilAccountLogout,
  cilCalendar,
  cilChartPie,
  cilCheckCircle,
  cilEducation,
  cilLibrary,
  cilPeople,
  cilRoom,
  cilSettings,
  cilSpeedometer,
  cilUser,
} from '@coreui/icons'
import { ROUTE_MY_SCHEDULES } from '../roleAccess'

export const ADMIN_NAVIGATION = Object.freeze([
  { path: '/dashboard', label: 'Painel', icon: cilSpeedometer },
  { path: '/schedules', label: 'Horários', icon: cilCalendar },
  { path: '/absences', label: 'Faltas', icon: cilCheckCircle },
  { path: '/timesheets', label: 'Fecho semanal', icon: cilCalendar },
  { section: 'Pedagogia' },
  { path: '/courses', label: 'Cursos', icon: cilEducation },
  { path: '/members', label: 'Equipa', icon: cilPeople },
  { path: '/subjects', label: 'Disciplinas', icon: cilLibrary },
  { section: 'Escola' },
  { path: '/rooms', label: 'Salas', icon: cilRoom },
  { path: '/config', label: 'Configuração', icon: cilSettings },
])

export const TEACHER_NAVIGATION = Object.freeze([
  { path: '/my-availability', label: 'Minha disponibilidade', icon: cilUser },
  { path: ROUTE_MY_SCHEDULES, label: 'Meus horários', icon: cilCalendar },
  { path: '/my-progress', label: 'Meu progresso', icon: cilChartPie },
])

export const SIGN_OUT_ICON = cilAccountLogout
