import React, { useState } from 'react'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput, 
  CFormCheck, CButton, CAlert
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSettings, cilSave } from '@coreui/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'

const SchoolConfig = () => {
  const queryClient = useQueryClient()
  const [successMsg, setSuccessMsg] = useState(null)
  
  // Estado inicial (Defaults comuns)
  const [formData, setFormData] = useState({
    start_time: '08:00',
    end_time: '18:00',
    slot_duration_minutes: 50, // Aula de 50min
    break_duration_minutes: 10, // Intervalo de 10min
    days: {0: true, 1: true, 2: true, 3: true, 4: true, 5: false, 6: false}
  })

  const mutation = useMutation({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post('/timeslots/generate', payload)
      return data
    },
    onSuccess: (data) => {
      setSuccessMsg("Configuração aplicada com sucesso! A grelha de horários foi regenerada.")
      queryClient.invalidateQueries(['timeslots']) // Limpa cache para a visualização
      setTimeout(() => setSuccessMsg(null), 3000)
    }
  })

  const handleSubmit = () => {
    const selectedDays = Object.keys(formData.days)
        .filter(d => formData.days[d])
        .map(d => parseInt(d))

    const payload = {
        start_time: formData.start_time + ':00',
        end_time: formData.end_time + ':00',
        slot_duration_minutes: parseInt(formData.slot_duration_minutes),
        break_duration_minutes: parseInt(formData.break_duration_minutes),
        days_of_week: selectedDays
    }
    mutation.mutate(payload)
  }

  const toggleDay = (idx) => {
    setFormData(prev => ({ ...prev, days: { ...prev.days, [idx]: !prev.days[idx] } }))
  }

  const daysLabel = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

  return (
    <div className="p-4">
      <h2 className="mb-4 fw-bold text-dark">
        <CIcon icon={cilSettings} className="me-2" />
        Configuração da Escola
      </h2>

      {successMsg && <CAlert color="success">{successMsg}</CAlert>}
      {mutation.isError && <CAlert color="danger">Erro ao guardar configuração.</CAlert>}

      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-white fw-bold py-3">
            Definição da Grelha Horária
        </CCardHeader>
        <CCardBody className="p-4">
            <p className="text-muted mb-4">
                Defina aqui o funcionamento geral da escola. Ao guardar, o sistema irá 
                <strong> regenerar todos os blocos horários</strong> base (Timeslots).
            </p>

            <CForm>
                <CRow className="mb-4">
                    <CCol md={3}>
                        <CFormInput type="time" label="Abertura da Escola" 
                            value={formData.start_time}
                            onChange={(e) => setFormData({...formData, start_time: e.target.value})}
                        />
                    </CCol>
                    <CCol md={3}>
                        <CFormInput type="time" label="Fecho da Escola" 
                            value={formData.end_time}
                            onChange={(e) => setFormData({...formData, end_time: e.target.value})}
                        />
                    </CCol>
                    <CCol md={3}>
                        <CFormInput type="number" label="Duração da Aula (min)" 
                            value={formData.slot_duration_minutes}
                            onChange={(e) => setFormData({...formData, slot_duration_minutes: e.target.value})}
                        />
                    </CCol>
                    <CCol md={3}>
                        <CFormInput type="number" label="Intervalo (min)" 
                            value={formData.break_duration_minutes}
                            onChange={(e) => setFormData({...formData, break_duration_minutes: e.target.value})}
                            text="Tempo de pausa entre aulas"
                        />
                    </CCol>
                </CRow>

                <div className="mb-4">
                    <label className="form-label fw-bold d-block mb-2">Dias de Funcionamento</label>
                    <div className="d-flex gap-2 flex-wrap">
                        {daysLabel.map((label, idx) => (
                            <CFormCheck 
                                key={idx}
                                button={{ color: formData.days[idx] ? 'primary' : 'secondary', variant: formData.days[idx] ? '' : 'outline' }}
                                type="checkbox" 
                                id={`day-${idx}`} 
                                label={label}
                                checked={formData.days[idx]}
                                onChange={() => toggleDay(idx)}
                            />
                        ))}
                    </div>
                </div>

                <div className="d-grid gap-2 d-md-flex justify-content-md-end">
                    <CButton color="primary" size="lg" onClick={handleSubmit} disabled={mutation.isPending}>
                        <CIcon icon={cilSave} className="me-2" />
                        {mutation.isPending ? 'A Processar...' : 'Guardar e Regenerar Grelha'}
                    </CButton>
                </div>
            </CForm>
        </CCardBody>
      </CCard>
    </div>
  )
}

export default SchoolConfig