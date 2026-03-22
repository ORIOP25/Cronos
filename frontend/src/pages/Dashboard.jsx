import React from 'react'

// Componentes do Projeto
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'

// CoreUI & Icons
import { 
  CCard, 
  CCardBody, 
  CCardHeader, 
  CContainer
} from '@coreui/react'

const Dashboard = () => {
  return (
    <CContainer fluid>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h2 className="mb-0 fw-bold text-dark">Painel de Controlo</h2>
      </div>

      <CCard className="mb-4 border-0 shadow-sm">
        <CCardHeader className="bg-white fw-bold py-3">Disponibilidade dos Professores</CCardHeader>
        <CCardBody>
            <AnalyticsHeatmap />
        </CCardBody>
      </CCard>
    </CContainer>
  )
}

export default Dashboard