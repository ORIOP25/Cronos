import React from 'react'
import { CContainer, CCard, CCardBody, CCardHeader } from '@coreui/react'
import AvailabilityGrid from '../components/AvailabilityGrid'

const MyAvailability = () => {
  return (
    <CContainer>
      <CCard className="mb-4">
        <CCardHeader>
          <strong>Definir Disponibilidade</strong>
        </CCardHeader>
        <CCardBody>
          <p className="text-muted mb-4">
            Defina as suas preferências clicando nos blocos abaixo.
          </p>
          <AvailabilityGrid />
        </CCardBody>
      </CCard>
    </CContainer>
  )
}

export default MyAvailability