import React, { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query' 
import apiClient from '../apiClient'
import {
  CRow, CCol, CCard, CCardBody, CSpinner, CAlert, CButton 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSave } from '@coreui/icons'

const daysOfWeek = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

const STATUS_COLORS = {
  available: 'light',
  unavailable: 'danger',
  preferred: 'warning'
}

// Função API para guardar
const saveAvailability = async (selections) => {
  // Converter o objeto { "1": "unavailable" } para array [{ timeslot_id: 1, status: "unavailable" }]
  const updates = Object.entries(selections).map(([id, status]) => ({
    timeslot_id: parseInt(id),
    status: status
  }))

  const response = await apiClient.post('/users/me/availability', updates)
  return response.data
}

const AvailabilityGrid = () => {
  const [selections, setSelections] = useState({})
  const [successMsg, setSuccessMsg] = useState('') // Mensagem de sucesso

  // Buscar Timeslots
  const { data: timeslots, isLoading, isError } = useQuery({
    queryKey: ['timeslots'],
    queryFn: async () => {
      const res = await apiClient.get('/import/timeslots')
      return res.data
    }
  })

  // Mutação para Guardar
  const mutation = useMutation({
    mutationFn: saveAvailability,
    onSuccess: (data) => {
      setSuccessMsg(data.message)
      setTimeout(() => setSuccessMsg(''), 3000)
    }
  })

  const toggleSlot = (slotId) => {
    setSelections(prev => {
      const current = prev[slotId] || 'available'
      let nextStatus = 'available'
      if (current === 'available') nextStatus = 'unavailable'
      else if (current === 'unavailable') nextStatus = 'preferred'
      else nextStatus = 'available'
      return { ...prev, [slotId]: nextStatus }
    })
  }

  // Organizar dados (igual a antes)
  const slotsByDay = (timeslots || []).reduce((acc, slot) => {
    if (!acc[slot.day_of_week]) acc[slot.day_of_week] = []
    acc[slot.day_of_week].push(slot)
    return acc
  }, {})
  Object.keys(slotsByDay).forEach(day => {
    slotsByDay[day].sort((a, b) => a.start_time.localeCompare(b.start_time))
  })

  if (isLoading) return <div className="text-center p-4"><CSpinner /> A carregar...</div>
  if (isError) return <CAlert color="danger">Erro ao carregar dados.</CAlert>

  return (
    <div>
      {/* BARRA DE AÇÃO */}
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div className="d-flex gap-2">
          <span className="badge bg-light text-dark border">Disponível</span>
          <span className="badge bg-danger">Indisponível</span>
          <span className="badge bg-warning text-dark">Preferencial</span>
        </div>
        
        <CButton 
          color="primary" 
          onClick={() => mutation.mutate(selections)}
          disabled={mutation.isPending || Object.keys(selections).length === 0}
        >
          {mutation.isPending ? <CSpinner size="sm"/> : <><CIcon icon={cilSave} className="me-2"/> Guardar Alterações</>}
        </CButton>
      </div>

      {mutation.isError && <CAlert color="danger">Erro ao guardar.</CAlert>}
      {successMsg && <CAlert color="success">{successMsg}</CAlert>}

      <CRow>
        {[0, 1, 2, 3, 4, 5].map(dayIndex => {
          const daySlots = slotsByDay[dayIndex]
          if (!daySlots || daySlots.length === 0) return null

          return (
            <CCol key={dayIndex} style={{ minWidth: '150px' }}>
              <h6 className="text-center mb-3">{daysOfWeek[dayIndex]}</h6>
              <div className="d-flex flex-column gap-2">
                {daySlots.map(slot => {
                  const status = selections[slot.id] || 'available'
                  const color = STATUS_COLORS[status]
                  
                  return (
                    <CCard 
                      key={slot.id} 
                      className={`text-center border-${color === 'light' ? 'secondary' : color} bg-${color}`}
                      style={{ cursor: 'pointer', transition: 'all 0.2s', userSelect: 'none' }}
                      onClick={() => toggleSlot(slot.id)}
                    >
                      <CCardBody className="p-2">
                        <small className="fw-bold">{slot.start_time.slice(0, 5)}</small>
                        <br/>
                        <small>{slot.end_time.slice(0, 5)}</small>
                      </CCardBody>
                    </CCard>
                  )
                })}
              </div>
            </CCol>
          )
        })}
      </CRow>
    </div>
  )
}

export default AvailabilityGrid