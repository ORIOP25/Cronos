import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../../apiClient' // Ajusta o caminho se necessário
import {
  CButton, CCol, CForm, CFormInput, CFormSelect, CAlert, CSpinner, CCard, CCardBody
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

// Função API específica para Timeslots
const createTimeslot = async (data) => {
  const response = await apiClient.post('/import/timeslot', data)
  return response.data
}

const TimeslotForm = () => {
  const [day, setDay] = useState(0) // 0 = Segunda
  const [start, setStart] = useState('08:30')
  const [end, setEnd] = useState('09:15')
  const [successMsg, setSuccessMsg] = useState('')

  const mutation = useMutation({
    mutationFn: createTimeslot,
    onSuccess: (data) => {
      setSuccessMsg(`Bloco criado com sucesso! (ID: ${data.id})`)
      setTimeout(() => setSuccessMsg(''), 3000)
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    // O backend espera inteiros para o dia da semana
    mutation.mutate({ 
        day_of_week: parseInt(day), 
        start_time: start + ":00", // Formato HH:MM:SS
        end_time: end + ":00" 
    })
  }

  return (
    <CCard className="mb-4 border-top-warning border-top-3">
      <CCardBody>
        <h5>Definir Blocos Horários</h5>
        <p className="text-muted small">Crie os tempos de aula (ex: 08:30 - 09:15).</p>

        {mutation.isError && (
          <CAlert color="danger">{mutation.error.response?.data?.detail || 'Erro.'}</CAlert>
        )}
        {successMsg && <CAlert color="success">{successMsg}</CAlert>}

        <CForm onSubmit={handleSubmit} className="row g-3">
          <CCol md={4}>
            <CFormSelect label="Dia da Semana" value={day} onChange={(e) => setDay(e.target.value)}>
              <option value={0}>Segunda-feira</option>
              <option value={1}>Terça-feira</option>
              <option value={2}>Quarta-feira</option>
              <option value={3}>Quinta-feira</option>
              <option value={4}>Sexta-feira</option>
              <option value={5}>Sábado</option>
            </CFormSelect>
          </CCol>
          <CCol md={3}>
            <CFormInput type="time" label="Início" value={start} onChange={(e) => setStart(e.target.value)} />
          </CCol>
          <CCol md={3}>
            <CFormInput type="time" label="Fim" value={end} onChange={(e) => setEnd(e.target.value)} />
          </CCol>
          <CCol md={2} className="d-flex align-items-end">
            <CButton color="warning" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? <CSpinner size="sm"/> : <CIcon icon={cilPlus}/>}
            </CButton>
          </CCol>
        </CForm>
      </CCardBody>
    </CCard>
  )
}

export default TimeslotForm