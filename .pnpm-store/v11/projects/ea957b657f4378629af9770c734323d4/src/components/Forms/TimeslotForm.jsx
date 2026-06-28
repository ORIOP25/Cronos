import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'

const TimeslotForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    day_of_week: 0, 
    start_time: '08:30',
    end_time: '09:15'
  })

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (initialData) {
      setFormData({
        day_of_week: initialData.day_of_week,
        start_time: initialData.start_time.substring(0, 5),
        end_time: initialData.end_time.substring(0, 5)
      })
    } else {
      setFormData({
        day_of_week: 0,
        start_time: '08:00',
        end_time: '08:45'
      })
    }
  }, [initialData])
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    // Enviar hora com segundos para o backend (HH:MM:00)
    // Opcional, mas o Pydantic gosta de formatos completos
    const payload = {
        day_of_week: Number.parseInt(formData.day_of_week, 10),
        start_time: formData.start_time.length === 5 ? formData.start_time + ':00' : formData.start_time,
        end_time: formData.end_time.length === 5 ? formData.end_time + ':00' : formData.end_time,
    }
    onSubmit(payload)
  }

  let submitLabel = 'Criar Bloco'
  if (isLoading) submitLabel = 'A gravar...'
  else if (initialData) submitLabel = 'Atualizar Bloco'

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={12}>
          <CFormSelect 
            id="timeslot-day"
            label="Dia da Semana" 
            name="day_of_week"
            value={formData.day_of_week}
            onChange={handleChange}
          >
            <option value="0">Segunda-feira</option>
            <option value="1">Terça-feira</option>
            <option value="2">Quarta-feira</option>
            <option value="3">Quinta-feira</option>
            <option value="4">Sexta-feira</option>
            <option value="5">Sábado</option>
            <option value="6">Domingo</option>
          </CFormSelect>
        </CCol>
        
        <CCol md={6}>
          <CFormInput
            id="timeslot-start-time"
            type="time"
            label="Hora Início"
            name="start_time"
            value={formData.start_time}
            onChange={handleChange}
            required
          />
        </CCol>
        
        <CCol md={6}>
          <CFormInput
            id="timeslot-end-time"
            type="time"
            label="Hora Fim"
            name="end_time"
            value={formData.end_time}
            onChange={handleChange}
            required
          />
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {submitLabel}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default TimeslotForm

TimeslotForm.propTypes = {
  initialData: PropTypes.object,
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}
