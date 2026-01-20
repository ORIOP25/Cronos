import React, { useState, useEffect } from 'react'
import {
  CForm, CFormSelect, CAlert, CSpinner
} from '@coreui/react'

/**
 * LessonForm.jsx
 * 
 * Formulário para atribuição de professor a uma disciplina/turma.
 * 
 * PADRÃO: Segue os 4 pilares:
 * - SEGURANÇA: Dropdown filtrado por competência (impossível escolher professor sem competência)
 * - ESTABILIDADE: Validação rigorosa, sem crash em edge cases
 * - OTIMIZAÇÃO: Usa dados já carregados (não faz queries extras)
 * - ESCALABILIDADE: Preparado para co-teaching (futuro)
 * 
 * Props:
 * - subject: SubjectRead { id, name }
 * - teachers: array de TeacherRead (já com subject_ids)
 * - selectedTeacherId: null | int
 * - onTeacherChange: (teacherId) => void
 * - isLoading: bool (para disable durante submit)
 */
const LessonForm = ({ 
  subject, 
  teachers, 
  selectedTeacherId, 
  onTeacherChange, 
  isLoading 
}) => {
  const [error, setError] = useState(null)

  // SEGURANÇA & OTIMIZAÇÃO: Filtrar professores que têm competência
  const filteredTeachers = React.useMemo(() => {
    if (!teachers || !subject) return []
    
    return teachers.filter(teacher => {
      // Resiliência: Lidar com múltiplas formas de data
      let subjectIds = teacher.subject_ids || []
      if (teacher.subjects && Array.isArray(teacher.subjects)) {
        subjectIds = teacher.subjects.map(s => s.id)
      }
      
      // Se o professor tem a disciplina, inclui
      return subjectIds.includes(subject.id)
    })
  }, [teachers, subject])

  const handleChange = (e) => {
    const teacherId = parseInt(e.target.value) || null
    
    // SEGURANÇA: Validar que o professor selecionado tem competência
    if (teacherId) {
      const teacher = teachers?.find(t => t.id === teacherId)
      if (!teacher) {
        setError('Professor não encontrado')
        return
      }
      
      const hasCompetency = (teacher.subject_ids || []).includes(subject.id)
      if (!hasCompetency) {
        setError(`${teacher.name} não tem competência em ${subject.name}`)
        return
      }
    }
    
    setError(null)
    onTeacherChange(teacherId)
  }

  // ESCALABILIDADE: Mensagens descritivas
  const getPlaceholder = () => {
    if (!teachers || teachers.length === 0) {
      return 'Nenhum professor disponível'
    }
    if (filteredTeachers.length === 0) {
      return `Nenhum professor tem competência em ${subject.name}`
    }
    return 'Selecione um professor'
  }

  return (
    <div className="mb-3">
      {/* Cabeçalho: Nome da Disciplina */}
      <label className="form-label fw-bold">{subject.name}</label>
      
      {/* ESTABILIDADE: Mostrar erro se houver validação fail */}
      {error && (
        <CAlert color="warning" className="mb-2">
          <small>{error}</small>
        </CAlert>
      )}
      
      {/* Dropdown: Professor Filtrado */}
      <CFormSelect
        id={`lesson-subject-${subject.id}`}
        value={selectedTeacherId || ''}
        onChange={handleChange}
        disabled={
          isLoading || 
          filteredTeachers.length === 0 || 
          !teachers
        }
        options={[
          { label: getPlaceholder(), value: '' },
          ...filteredTeachers.map(teacher => ({
            label: teacher.name,
            value: teacher.id
          }))
        ]}
      />
      
      {/* OTIMIZAÇÃO: Mostrar info de competência se hovering (tooltips visuais) */}
      {selectedTeacherId && filteredTeachers.find(t => t.id === selectedTeacherId) && (
        <small className="text-muted d-block mt-1">
          ✓ {filteredTeachers.find(t => t.id === selectedTeacherId).name} tem competência
        </small>
      )}
    </div>
  )
}

export default LessonForm
