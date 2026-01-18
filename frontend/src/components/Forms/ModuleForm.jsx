import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CFormSelect, CButton, CModalFooter, CSpinner
} from '@coreui/react'
import { useSubjects } from '../../hooks/useSchoolData'

const ModuleForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '',
    code: '',
    hours_total: '',
    subject_id: ''
  })

  // Carregar disciplinas para o dropdown
  const { data: subjects, isLoading: subjectsLoading } = useSubjects()

  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        code: initialData.code || '',
        hours_total: initialData.hours_total || '',
        subject_id: initialData.subject_id || ''
      })
    } else {
      setFormData({ 
        name: '',
        code: '',
        hours_total: '',
        subject_id: ''
      })
    }
  }, [initialData])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    
    // Validação: horas deve ser > 0
    if (formData.hours_total && parseFloat(formData.hours_total) <= 0) {
      alert('A carga horária deve ser superior a 0')
      return
    }

    // Enviar dados
    onSubmit({
      ...formData,
      hours_total: parseFloat(formData.hours_total)
    })
  }

  if (subjectsLoading) {
    return <div className="text-center p-5"><CSpinner color="primary" /></div>
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        
        <CCol md={6}>
          <CFormSelect 
            label="Disciplina Associada"
            name="subject_id"
            value={formData.subject_id}
            onChange={handleChange}
            required
            text="Selecione a disciplina"
          >
            <option value="">-- Selecione --</option>
            {(subjects || []).map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </CFormSelect>
        </CCol>

        <CCol md={6}>
          <CFormInput
            type="text"
            label="Código UFCD"
            name="code"
            value={formData.code}
            onChange={handleChange}
            placeholder="Ex: 0789"
            text="Opcional - Identificador único do módulo"
          />
        </CCol>

        <CCol md={12}>
          <CFormInput
            type="text"
            label="Nome do Módulo"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: Fundamentos de C++"
          />
        </CCol>

        <CCol md={6}>
          <CFormInput
            type="number"
            label="Carga Horária Total"
            name="hours_total"
            value={formData.hours_total}
            onChange={handleChange}
            required
            placeholder="Ex: 50"
            text="Horas totais do módulo"
            step="0.5"
            min="0.5"
          />
        </CCol>

      </CRow>

      <CModalFooter className="mt-4">
        <CButton color="secondary" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'A guardar...' : 'Guardar'}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default ModuleForm
