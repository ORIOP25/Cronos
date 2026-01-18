import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CSpinner, CListGroup, CListGroupItem, CFormCheck
} from '@coreui/react'
import { useSubjects } from '../../hooks/useSchoolData'

const CourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '',
    subject_ids: []
  })

  const { data: subjects, isLoading: subjectsLoading } = useSubjects()

  useEffect(() => {
    if (initialData) {
      // Lógica de Normalização (Resiliência):
      // O backend pode enviar 'subjects' (lista de objetos) ou 'subject_ids' (lista de ints).
      // Nós queremos sempre uma lista de ints para as checkboxes.
      let normalizedIds = [];

      if (initialData.subject_ids && Array.isArray(initialData.subject_ids)) {
        // Caso 1: Veio lista de IDs simples
        normalizedIds = initialData.subject_ids;
      } else if (initialData.subjects && Array.isArray(initialData.subjects)) {
        // Caso 2: Vieram objetos completos (devido ao selectinload do backend)
        normalizedIds = initialData.subjects.map(s => s.id);
      }

      setFormData({
        name: initialData.name || '',
        subject_ids: normalizedIds
      })
    } else {
        // Modo Criação
        setFormData({ name: '', subject_ids: [] })
    }
  }, [initialData])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubjectToggle = (subjectId) => {
    setFormData(prev => ({
      ...prev,
      subject_ids: prev.subject_ids.includes(subjectId)
        ? prev.subject_ids.filter(id => id !== subjectId)
        : [...prev.subject_ids, subjectId]
    }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  if (subjectsLoading) {
    return <div className="text-center p-5"><CSpinner color="primary" /></div>
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        
        <CCol md={12}>
          <CFormInput
            type="text"
            label="Nome do Curso"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: Técnico de Gestão e Programação"
          />
        </CCol>

        <CCol md={12}>
          <label className="form-label fw-bold">Estrutura Curricular (Disciplinas)</label>
          <p className="text-muted small">Selecione todas as disciplinas que compõem este curso:</p>
          
          {subjects && subjects.length > 0 ? (
            <CListGroup>
              {subjects.map(subject => (
                <CListGroupItem key={subject.id} className="py-2">
                  <div className="form-check">
                    <CFormCheck
                      type="checkbox"
                      id={`subject-${subject.id}`}
                      label={subject.name}
                      checked={formData.subject_ids.includes(subject.id)}
                      onChange={() => handleSubjectToggle(subject.id)}
                    />
                  </div>
                </CListGroupItem>
              ))}
            </CListGroup>
          ) : (
            <p className="text-muted">Nenhuma disciplina disponível. Cria-as primeiro!</p>
          )}

          {formData.subject_ids.length > 0 && (
            <p className="text-info small mt-2">
              ✓ {formData.subject_ids.length} disciplina(s) selecionada(s)
            </p>
          )}
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

export default CourseForm

