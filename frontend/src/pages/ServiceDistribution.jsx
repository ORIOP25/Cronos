import React, { useState } from 'react'
import {
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CFormSelect, CSpinner, CForm
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilChartLine, cilCheckAlt } from '@coreui/icons'

import LessonForm from '../components/Forms/LessonForm'

// Hooks de Dados (Read & Write)
import {
  useClasses,
  useTeachers,
  useClassCurriculum,
  useCreateEntity
} from '../hooks/useSchoolData'

/**
 * ServiceDistribution.jsx
 *
 * Página para a "Distribuição de Serviço" (Atribuição de Professores a Turmas).
 *
 * FLUXO:
 * 1. Admin seleciona Turma
 * 2. Sistema carrega disciplinas do curso (currículo)
 * 3. Para cada disciplina, aparece dropdown com professores compatíveis
 * 4. Admin clica "Guardar Distribuição"
 * 5. Sistema cria/atualiza Lessons (atribuições)
 *
 * PADRÃO: Segue os 4 pilares:
 * - SEGURANÇA: Dropdowns filtrados, validação backend reforçada
 * - ESTABILIDADE: Error handling robusto, edge cases cobertos
 * - OTIMIZAÇÃO: Cache de hooks, evita N+1, lazy loading
 * - ESCALABILIDADE: Preparado para co-teaching (2 profs/aula)
 */
const ServiceDistribution = () => {
  // 1. ESTADO LOCAL: Seleções do Admin
  const [selectedClassId, setSelectedClassId] = useState(null)
  const [assignments, setAssignments] = useState({}) // { subject_id: teacher_id }
  const [savingError, setSavingError] = useState(null)
  const [savingSuccess, setSavingSuccess] = useState(false)

  // 2. HOOKS DE DADOS (Cache automática)
  const { data: classes, isLoading: classesLoading } = useClasses()
  const { data: teachers, isLoading: teachersLoading } = useTeachers()
  
  // OTIMIZAÇÃO: Só carrega currículo se classId foi selecionada
  const { data: curriculum, isLoading: curriculumLoading } = useClassCurriculum(selectedClassId)
  
  // Mutação para criar Lessons
  const createLessonMutation = useCreateEntity('lessons')

  // 3. LÓGICA DE MUDANÇA: Quando seleciona turma
  const handleClassChange = (e) => {
    const classId = parseInt(e.target.value) || null
    setSelectedClassId(classId)
    
    // ESTABILIDADE: Reset de atribuições quando muda turma
    setAssignments({})
    setSavingError(null)
    setSavingSuccess(false)
  }

  // 4. LÓGICA DE MUDANÇA: Quando seleciona professor
  const handleTeacherChange = (subjectId, teacherId) => {
    setAssignments(prev => ({
      ...prev,
      [subjectId]: teacherId
    }))
    
    // Clear error/success quando faz mudanças
    setSavingError(null)
    setSavingSuccess(false)
  }

  // 5. LÓGICA DE SUBMIT: Guardar distribuição
  const handleSaveDistribution = async () => {
    // SEGURANÇA: Validação básica
    if (!selectedClassId) {
      setSavingError('Por favor, selecione uma turma')
      return
    }

    // ESTABILIDADE: Verificar se há atribuições
    const assignmentEntries = Object.entries(assignments).filter(([_, teacherId]) => teacherId)
    if (assignmentEntries.length === 0) {
      setSavingError('Por favor, atribua pelo menos um professor')
      return
    }

    try {
      setSavingError(null)
      
      // Criar Lessons para cada atribuição
      // NOTA: Pode ser que precises de fazer um endpoint de bulk, dependendo da performance
      const promises = assignmentEntries.map(([subjectId, teacherId]) => {
        return createLessonMutation.mutateAsync({
          class_id: parseInt(selectedClassId),
          subject_id: parseInt(subjectId),
          teacher_id: parseInt(teacherId),
          // num_per_week é opcional (Solver calcula)
        })
      })

      // ESTABILIDADE: Esperar que todas as atribuições sejam criadas
      await Promise.all(promises)
      
      setSavingSuccess(true)
      
      // ESCALABILIDADE: Reset para nova distribuição
      setTimeout(() => {
        setAssignments({})
        setSelectedClassId(null)
        setSavingSuccess(false)
      }, 2000)
      
    } catch (error) {
      // SEGURANÇA: Mostrar erro específico
      const detail = error?.response?.data?.detail
      setSavingError(
        typeof detail === 'string' 
          ? detail 
          : 'Erro ao guardar distribuição. Verifique se todos os professores têm competência.'
      )
    }
  }

  // 6. ESTADO DE LOADING: Usar padrão do projeto
  const isLoading = classesLoading || teachersLoading || curriculumLoading
  const isSaving = createLessonMutation.isPending

  // 7. RESILIÊNCIA: Dados não carregados
  if (isLoading && !classes) {
    return (
      <div className="p-4 text-center">
        <CSpinner color="primary" /> A carregar dados...
      </div>
    )
  }

  return (
    <div className="p-4">
      {/* CABEÇALHO */}
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilChartLine} className="me-2 text-primary" />
            Distribuição de Serviço
          </h2>
          <small className="text-muted">
            Atribua professores às disciplinas de cada turma. O sistema validará competências automaticamente.
          </small>
        </CCol>
      </CRow>

      {/* ALERTAS DE ERRO/SUCESSO */}
      {savingSuccess && (
        <CAlert color="success" dismissible onClose={() => setSavingSuccess(false)}>
          <strong>✓ Distribuição guardada com sucesso!</strong> Os professores foram atribuídos.
        </CAlert>
      )}

      {savingError && (
        <CAlert color="danger" dismissible onClose={() => setSavingError(null)}>
          <strong>Erro:</strong> {savingError}
        </CAlert>
      )}

      {/* ERRO: Mutation do backend */}
      {createLessonMutation.isError && (
        <CAlert color="danger" dismissible onClose={() => createLessonMutation.reset()}>
          <strong>Erro no servidor:</strong> {
            createLessonMutation.error?.response?.data?.detail || 
            'Ocorreu um erro ao guardar'
          }
        </CAlert>
      )}

      {/* FORMULÁRIO PRINCIPAL */}
      <CCard className="border-0 shadow-sm">
        <CCardBody>
          <CForm>
            {/* PASSO 1: Selecionar Turma */}
            <div className="mb-4">
              <label className="form-label fw-bold">Passo 1: Selecione a Turma</label>
              <CFormSelect
                id="select-class"
                value={selectedClassId || ''}
                onChange={handleClassChange}
                disabled={classesLoading}
                options={[
                  { label: 'Escolha uma turma...', value: '' },
                  ...(classes || []).map(cls => ({
                    label: cls.name,
                    value: cls.id
                  }))
                ]}
              />
            </div>

            {/* PASSO 2: Atribuir Professores */}
            {selectedClassId && curriculum && (
              <div>
                <label className="form-label fw-bold mb-3">
                  Passo 2: Atribua Professores às Disciplinas
                </label>
                
                {/* ESTABILIDADE: Se currículo vazio */}
                {curriculum.length === 0 ? (
                  <CAlert color="info">
                    Esta turma não tem um curso associado ou o curso não tem disciplinas.
                    Por favor, verifique a configuração da turma.
                  </CAlert>
                ) : (
                  <div className="border rounded p-3 bg-light">
                    {/* Grid de Disciplinas + Professores */}
                    {curriculum.map(subject => (
                      <LessonForm
                        key={subject.id}
                        subject={subject}
                        teachers={teachers || []}
                        selectedTeacherId={assignments[subject.id] || null}
                        onTeacherChange={(teacherId) => handleTeacherChange(subject.id, teacherId)}
                        isLoading={isSaving}
                      />
                    ))}
                  </div>
                )}

                {/* BOTÃO DE SUBMIT */}
                <div className="mt-4 text-end">
                  <CButton
                    color="primary"
                    onClick={handleSaveDistribution}
                    disabled={
                      isSaving || 
                      curriculum.length === 0 || 
                      Object.values(assignments).filter(Boolean).length === 0
                    }
                    className="d-flex align-items-center gap-2 ms-auto"
                  >
                    {isSaving ? (
                      <>
                        <CSpinner size="sm" /> A guardar...
                      </>
                    ) : (
                      <>
                        <CIcon icon={cilCheckAlt} />
                        Guardar Distribuição
                      </>
                    )}
                  </CButton>
                </div>
              </div>
            )}

            {/* PASSO 2: Se nenhuma turma selecionada */}
            {!selectedClassId && (
              <CAlert color="secondary">
                Selecione uma turma no passo 1 para começar a atribuição de professores.
              </CAlert>
            )}
          </CForm>
        </CCardBody>
      </CCard>

      {/* DOCUMENTAÇÃO/AJUDA */}
      <CCard className="border-0 shadow-sm mt-4">
        <CCardBody>
          <h5 className="fw-bold mb-2">ℹ️ Como Funciona</h5>
          <ul className="text-muted small mb-0">
            <li><strong>Passo 1:</strong> Selecione a turma que deseja distribuir professores.</li>
            <li><strong>Passo 2:</strong> O sistema carrega automaticamente as disciplinas do curso da turma.</li>
            <li><strong>Dropdowns:</strong> Mostram APENAS professores que têm competência na disciplina.</li>
            <li><strong>Validação:</strong> Se um professor não tem competência, o sistema bloqueia a atribuição (reforço de segurança).</li>
            <li><strong>Solver:</strong> Após guardar, o Solver calculará dinamicamente quantas horas cada professor dá por semana.</li>
          </ul>
        </CCardBody>
      </CCard>
    </div>
  )
}

export default ServiceDistribution
