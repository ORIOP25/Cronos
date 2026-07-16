import { CButton } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowLeft, cilArrowRight } from '@coreui/icons'
import { addDays, formatWeekRange, getCurrentWeekMonday } from '../utils/formatUtils'

const WeekNavigator = ({ value, onChange }) => (
  <div className="d-flex align-items-center gap-2" aria-label="Navegação semanal">
    <CButton color="secondary" variant="outline" size="sm" onClick={() => onChange(addDays(value, -7))} aria-label="Semana anterior"><CIcon icon={cilArrowLeft} /></CButton>
    <span className="small fw-semibold text-center" style={{ minWidth: '200px' }}>{formatWeekRange(value)}</span>
    <CButton color="secondary" variant="outline" size="sm" onClick={() => onChange(addDays(value, 7))} aria-label="Próxima semana"><CIcon icon={cilArrowRight} /></CButton>
    <CButton color="secondary" variant="outline" size="sm" onClick={() => onChange(getCurrentWeekMonday())}>Hoje</CButton>
  </div>
)

export default WeekNavigator
