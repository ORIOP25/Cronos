import React from 'react'
import { CCard, CCardBody, CAlert } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCalendar } from '@coreui/icons'
import { useTimeslots } from '../hooks/useSchoolData'
import TimeGrid from '../components/TimeGrid'

const Schedules = () => {
  const { data: timeslots, isLoading } = useTimeslots()

  return (
    <div className="p-4">
       <div className="d-flex justify-content-between align-items-center mb-4">
          <div>
            <h2 className="mb-0 fw-bold text-dark">
                <CIcon icon={cilCalendar} className="me-2 text-primary" />
                Horários Escolares
            </h2>
            <small className="text-muted">Visualização da grelha de aulas (Modo Leitura).</small>
          </div>
       </div>

      <CAlert color="info">
        <strong>Modo de Visualização:</strong> Nesta fase, esta grelha mostra a estrutura de tempos definida na Configuração. Após a geração automática, as aulas aparecerão aqui.
      </CAlert>

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
            {isLoading ? (
                <div className="p-5 text-center">A carregar grelha...</div>
            ) : (
                <TimeGrid timeslots={timeslots || []} />
            )}
        </CCardBody>
      </CCard>
    </div>
  )
}

export default Schedules