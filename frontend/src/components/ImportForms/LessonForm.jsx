import React, { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import {
  CButton, CCol, CForm, CFormSelect, CFormInput, CFormCheck, CAlert, CSpinner, CCard, CCardBody
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

// --- API Calls ---
const fetchLists = async () => {
  // Vamos buscar as 3 listas em paralelo
  const [teachers, classes, subjects] = await Promise.all([
    apiClient.get('/import/teachers').then(r => r.data),
    apiClient.get('/import/classes').then(r => r.data),
    apiClient.get('/import/subjects').then(r => r.data)
  ])
  return { teachers, classes, subjects }
}

const createLesson = async (data) => {
  const response = await apiClient.post('/import/lesson', data)
  return response.data
}

const LessonForm = () => {
  // Estado do formulário
  const [classId, setClassId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [teacherId, setTeacherId] = useState('')
  const [numPerWeek, setNumPerWeek] = useState(1)
  const [isDouble, setIsDouble] = useState(false)
  const [successMsg, setSuccessMsg] = useState('')

  // 1. QUERY: Buscar as listas para os dropdowns
  const { data: lists, isLoading, isError } = useQuery({
    queryKey: ['importLists'],
    queryFn: fetchLists
  })

  // 2. MUTATION: Criar a aula
  const mutation = useMutation({
    mutationFn: createLesson,
    onSuccess: (data) => {
      setSuccessMsg(`Aula criada com sucesso! (ID: ${data.id})`)
      setTimeout(() => setSuccessMsg(''), 3000)
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    mutation.mutate({
      class_id: parseInt(classId),
      subject_id: parseInt(subjectId),
      teacher_id: parseInt(teacherId),
      num_per_week: parseInt(numPerWeek),
      is_double: isDouble
    })
  }

  if (isLoading) return <div className="text-center p-3"><CSpinner /> A carregar listas...</div>
  if (isError) return <CAlert color="danger">Erro ao carregar dados. Verifique se criou Professores, Turmas e Disciplinas.</CAlert>

  return (
    <CCard className="mb-4 border-top-info border-top-3">
      <CCardBody>
        <h5>Definir Aulas (Necessidades)</h5>
        <p className="text-muted small">Ex: A Turma X tem Matemática com o Prof. Y, 3 vezes por semana.</p>

        {mutation.isError && <CAlert color="danger">{mutation.error.response?.data?.detail || 'Erro.'}</CAlert>}
        {successMsg && <CAlert color="success">{successMsg}</CAlert>}

        <CForm onSubmit={handleSubmit} className="row g-3">
          
          {/* Dropdown Turma */}
          <CCol md={3}>
            <CFormSelect label="Turma" value={classId} onChange={(e) => setClassId(e.target.value)} required>
              <option value="">Selecione...</option>
              {lists.classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </CFormSelect>
          </CCol>

          {/* Dropdown Disciplina */}
          <CCol md={3}>
            <CFormSelect label="Disciplina" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} required>
              <option value="">Selecione...</option>
              {lists.subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </CFormSelect>
          </CCol>

          {/* Dropdown Professor */}
          <CCol md={3}>
            <CFormSelect label="Professor" value={teacherId} onChange={(e) => setTeacherId(e.target.value)} required>
              <option value="">Selecione...</option>
              {lists.teachers.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </CFormSelect>
          </CCol>

          {/* Configurações */}
          <CCol md={3}>
            <CFormInput 
              type="number" 
              label="Aulas / Semana" 
              min="1" 
              value={numPerWeek} 
              onChange={(e) => setNumPerWeek(e.target.value)} 
            />
            <CFormCheck 
              id="isDouble" 
              label="Bloco Duplo?" 
              className="mt-2"
              checked={isDouble}
              onChange={(e) => setIsDouble(e.target.checked)}
            />
          </CCol>

          <CCol md={12} className="text-end">
            <CButton color="info" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? <CSpinner size="sm"/> : <><CIcon icon={cilPlus}/> Criar Aula</>}
            </CButton>
          </CCol>
        </CForm>
      </CCardBody>
    </CCard>
  )
}

export default LessonForm